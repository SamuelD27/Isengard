#!/bin/bash
###############################################################################
# Isengard Bootstrap v2 - Single Authoritative Pod Startup Script
# Location: /runpod-volume/isengard/bootstrap_v2.sh
#
# This script handles ALL startup requirements:
# - Environment setup (secrets, env vars)
# - Dependency verification
# - Submodule/repo setup
# - Virtual environments
# - Model symlinks
# - Service orchestration
# - Health checks
# - E2E smoke test
#
# Usage: ./bootstrap_v2.sh [--skip-e2e] [--restart-only]
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
VOLUME_ROOT="/runpod-volume/isengard"
APP_ROOT="/app"
COMFYUI_ROOT="/opt/ComfyUI"
VENVS_DIR="${VOLUME_ROOT}/.venvs"
AITOOLKIT_VENV="${VENVS_DIR}/aitoolkit"
AITOOLKIT_REPO="${VOLUME_ROOT}/ai-toolkit"
LOGS_DIR="${VOLUME_ROOT}/logs"
CACHE_DIR="${VOLUME_ROOT}/.cache"

# Service PIDs file
PIDS_FILE="${VOLUME_ROOT}/.service_pids"

###############################################################################
# Helper Functions
###############################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo ""
    echo -e "${GREEN}===========================================================================${NC}"
    echo -e "${GREEN}  $1${NC}"
    echo -e "${GREEN}===========================================================================${NC}"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 available"
        return 0
    else
        log_error "$1 not found"
        return 1
    fi
}

wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=${3:-30}
    local count=0

    # Use curl instead of nc (nc may not be available)
    while ! curl -sf "http://localhost:${port}" > /dev/null 2>&1; do
        if [ $count -ge $max_wait ]; then
            # Try ss as fallback check
            if ss -tlnp | grep -q ":${port}"; then
                log_success "$name listening on port $port (ss check)"
                return 0
            fi
            log_error "$name did not start on port $port within ${max_wait}s"
            return 1
        fi
        sleep 1
        count=$((count + 1))
    done
    log_success "$name listening on port $port"
    return 0
}

###############################################################################
# Phase 1: Environment Setup
###############################################################################

setup_environment() {
    log_section "Phase 1: Environment Setup"

    # Create directory structure
    mkdir -p "${VOLUME_ROOT}"/{uploads,loras,outputs,configs,logs,.cache/huggingface}
    mkdir -p "${LOGS_DIR}"/{api,worker,comfyui,web}

    # Load secrets if available
    if [ -f /secrets.sh ]; then
        log_info "Loading /secrets.sh"
        source /secrets.sh
        log_success "Secrets loaded"
    else
        log_warn "/secrets.sh not found - some features may not work"
    fi

    # Set required environment variables
    export ISENGARD_MODE="${ISENGARD_MODE:-production}"
    export VOLUME_ROOT="${VOLUME_ROOT}"
    export DATA_DIR="${VOLUME_ROOT}"
    export HF_HOME="${CACHE_DIR}/huggingface"
    export COMFYUI_URL="http://localhost:8188"
    export REDIS_URL="redis://localhost:6379"
    export PYTHONUNBUFFERED=1
    export PYTHONDONTWRITEBYTECODE=1

    # Verify HF_TOKEN for FLUX.1-dev access
    if [ -n "$HF_TOKEN" ]; then
        log_success "HF_TOKEN is set"
    else
        log_warn "HF_TOKEN not set - FLUX.1-dev downloads will fail"
    fi

    log_success "Environment configured (ISENGARD_MODE=${ISENGARD_MODE})"
}

###############################################################################
# Phase 2: AI-Toolkit Setup
###############################################################################

setup_aitoolkit() {
    log_section "Phase 2: AI-Toolkit Repository & Venv"

    # Clone or update AI-Toolkit repo
    if [ -d "${AITOOLKIT_REPO}/.git" ]; then
        log_info "AI-Toolkit repo exists, checking for updates..."
        cd "${AITOOLKIT_REPO}"
        git fetch origin 2>/dev/null || log_warn "Could not fetch updates"
        log_success "AI-Toolkit repo ready at ${AITOOLKIT_REPO}"
    else
        log_info "Cloning AI-Toolkit repository..."
        rm -rf "${AITOOLKIT_REPO}"
        git clone https://github.com/ostris/ai-toolkit.git "${AITOOLKIT_REPO}"
        log_success "AI-Toolkit cloned to ${AITOOLKIT_REPO}"
    fi

    # Create or verify venv
    if [ -f "${AITOOLKIT_VENV}/bin/python" ]; then
        log_success "AI-Toolkit venv exists at ${AITOOLKIT_VENV}"
    else
        log_info "Creating AI-Toolkit venv..."
        python3.11 -m venv --system-site-packages "${AITOOLKIT_VENV}"
        log_success "AI-Toolkit venv created"
    fi

    # Install/update dependencies
    log_info "Installing AI-Toolkit dependencies..."
    "${AITOOLKIT_VENV}/bin/pip" install --quiet --upgrade pip

    # AI-Toolkit uses requirements.txt, not setup.py/pyproject.toml
    if [ -f "${AITOOLKIT_REPO}/requirements.txt" ]; then
        "${AITOOLKIT_VENV}/bin/pip" install --quiet -r "${AITOOLKIT_REPO}/requirements.txt"
    fi

    # Ensure the toolkit module is on PYTHONPATH by adding .pth file
    local site_packages=$("${AITOOLKIT_VENV}/bin/python" -c "import site; print(site.getsitepackages()[0])")
    echo "${AITOOLKIT_REPO}" > "${site_packages}/aitoolkit.pth"
    log_info "Added AI-Toolkit to PYTHONPATH via .pth file"

    # Verify toolkit module is importable
    if "${AITOOLKIT_VENV}/bin/python" -c "import toolkit; print('toolkit OK')" 2>/dev/null; then
        log_success "AI-Toolkit module importable"
    else
        log_error "AI-Toolkit module import failed!"
        return 1
    fi
}

###############################################################################
# Phase 3: Patch AI-Toolkit Plugin
###############################################################################

patch_aitoolkit_plugin() {
    log_section "Phase 3: Patch AI-Toolkit Plugin"

    local plugin_file="${APP_ROOT}/packages/plugins/training/src/ai_toolkit.py"

    if [ ! -f "$plugin_file" ]; then
        log_error "AI-Toolkit plugin not found at $plugin_file"
        return 1
    fi

    # Check if already patched
    if grep -q "aitoolkit_venv_python" "$plugin_file"; then
        log_success "Plugin already patched"
        return 0
    fi

    log_info "Patching AI-Toolkit plugin..."

    # Backup original
    cp "$plugin_file" "${plugin_file}.backup"

    # Create patched version using Python
    python3 << 'PATCHEOF'
import re

plugin_file = "/app/packages/plugins/training/src/ai_toolkit.py"

with open(plugin_file, 'r') as f:
    content = f.read()

# Find and replace the subprocess command section
old_pattern = r'cmd = \["python", "-m", "toolkit\.job", str\(config_path\)\]'
new_cmd = '''# AI-Toolkit venv and run.py path (configured for pod isolation)
        aitoolkit_venv_python = "/runpod-volume/isengard/.venvs/aitoolkit/bin/python"
        aitoolkit_run_py = "/runpod-volume/isengard/ai-toolkit/run.py"
        cmd = [aitoolkit_venv_python, aitoolkit_run_py, str(config_path)]'''

content = re.sub(old_pattern, new_cmd, content)

# Also update the subprocess call to include cwd and HF_HOME
old_subprocess = r'process = subprocess\.Popen\(\s*cmd,\s*stdout=subprocess\.PIPE,\s*stderr=subprocess\.STDOUT,\s*text=True,\s*bufsize=1,\s*'
if 'cwd="/runpod-volume' not in content:
    content = re.sub(
        r'(process = subprocess\.Popen\(\s*cmd,\s*stdout=subprocess\.PIPE,\s*stderr=subprocess\.STDOUT,\s*text=True,\s*bufsize=1,)',
        r'\1\n            cwd="/runpod-volume/isengard/ai-toolkit",\n            env={**os.environ, "PYTHONUNBUFFERED": "1", "HF_HOME": "/runpod-volume/isengard/.cache/huggingface"},',
        content
    )

with open(plugin_file, 'w') as f:
    f.write(content)

print("Plugin patched successfully")
PATCHEOF

    log_success "Plugin patched"
}

###############################################################################
# Phase 4: Model Symlinks
###############################################################################

setup_model_symlinks() {
    log_section "Phase 4: Model Symlinks"

    local comfyui_models="${COMFYUI_ROOT}/models"
    local comfyui_loras="${comfyui_models}/loras"

    # Create loras directory if needed
    mkdir -p "${comfyui_loras}"

    # Symlink trained LoRAs to ComfyUI
    log_info "Setting up LoRA symlinks..."

    local lora_count=0
    if [ -d "${VOLUME_ROOT}/loras" ]; then
        for char_dir in "${VOLUME_ROOT}/loras"/char-*; do
            if [ -d "$char_dir" ]; then
                local char_id=$(basename "$char_dir")
                for safetensor in "$char_dir"/*.safetensors; do
                    if [ -f "$safetensor" ]; then
                        local lora_name="${char_id}_$(basename "$safetensor")"
                        local link_path="${comfyui_loras}/${lora_name}"

                        if [ ! -L "$link_path" ]; then
                            ln -sf "$safetensor" "$link_path"
                            log_info "Linked: $lora_name"
                        fi
                        lora_count=$((lora_count + 1))
                    fi
                done
            fi
        done
    fi

    log_success "LoRA symlinks configured (${lora_count} found)"

    # Create UNET symlinks (workflows may use UNETLoader instead of CheckpointLoader)
    local flux_unet="${comfyui_models}/unet"
    mkdir -p "${flux_unet}"

    # Symlink from checkpoints to unet (FLUX models work in both locations)
    local volume_checkpoints="/runpod-volume/isengard/comfyui/models/checkpoints"
    if [ -f "${volume_checkpoints}/flux1-dev.safetensors" ]; then
        ln -sf "${volume_checkpoints}/flux1-dev.safetensors" "${flux_unet}/flux1-dev.safetensors"
        log_info "Linked FLUX.1-dev to unet folder"
    fi
    if [ -f "${volume_checkpoints}/flux1-schnell.safetensors" ]; then
        ln -sf "${volume_checkpoints}/flux1-schnell.safetensors" "${flux_unet}/flux1-schnell.safetensors"
        log_info "Linked FLUX.1-schnell to unet folder"
    fi

    # Verify FLUX models
    log_info "Verifying FLUX models..."
    local models_ok=true

    # Check both unet and checkpoints folders
    if [ -f "${flux_unet}/flux1-dev.safetensors" ] || [ -f "${comfyui_models}/checkpoints/flux1-dev.safetensors" ]; then
        log_success "FLUX.1-dev present"
    else
        log_warn "FLUX.1-dev missing"
        models_ok=false
    fi

    if [ -f "${flux_unet}/flux1-schnell.safetensors" ] || [ -f "${comfyui_models}/checkpoints/flux1-schnell.safetensors" ]; then
        log_success "FLUX.1-schnell present"
    else
        log_warn "FLUX.1-schnell missing"
        models_ok=false
    fi

    local flux_vae="${comfyui_models}/vae"
    if [ -f "${flux_vae}/ae.safetensors" ]; then
        log_success "FLUX VAE present"
    else
        log_warn "FLUX VAE missing"
        models_ok=false
    fi

    local flux_clip="${comfyui_models}/clip"
    if [ -f "${flux_clip}/clip_l.safetensors" ] && [ -f "${flux_clip}/t5xxl_fp16.safetensors" ]; then
        log_success "FLUX CLIP models present"
    else
        log_warn "FLUX CLIP models missing"
        models_ok=false
    fi

    if [ "$models_ok" = true ]; then
        log_success "All required models present"
    else
        log_warn "Some models missing - generation may fail"
    fi
}

###############################################################################
# Phase 5: Stop Existing Services
###############################################################################

stop_services() {
    log_section "Phase 5: Stopping Existing Services"

    # Kill by known patterns
    log_info "Stopping existing services..."

    # API
    pkill -f "uvicorn.*8000" 2>/dev/null && log_info "Stopped API" || true

    # Worker
    pkill -f "python.*worker" 2>/dev/null && log_info "Stopped Worker" || true
    pkill -f "python -m apps.worker" 2>/dev/null || true

    # ComfyUI
    pkill -f "python.*ComfyUI" 2>/dev/null && log_info "Stopped ComfyUI" || true
    pkill -f "main.py.*8188" 2>/dev/null || true

    # Web
    pkill -f "node.*vite" 2>/dev/null && log_info "Stopped Web" || true
    pkill -f "npm.*dev" 2>/dev/null || true

    # Wait for ports to be released
    sleep 2

    log_success "Existing services stopped"
}

###############################################################################
# Phase 6: Start Services
###############################################################################

start_services() {
    log_section "Phase 6: Starting Services"

    # Clear PIDs file
    > "${PIDS_FILE}"

    # 1. Redis (usually already running from container)
    log_info "Checking Redis..."
    if redis-cli ping &>/dev/null; then
        log_success "Redis already running"
    else
        log_info "Starting Redis..."
        redis-server --daemonize yes
        sleep 1
        if redis-cli ping &>/dev/null; then
            log_success "Redis started"
        else
            log_error "Redis failed to start"
            return 1
        fi
    fi

    # 2. ComfyUI
    log_info "Starting ComfyUI..."
    cd "${COMFYUI_ROOT}"
    nohup python main.py --listen 0.0.0.0 --port 8188 \
        > "${LOGS_DIR}/comfyui/comfyui.log" 2>&1 &
    echo "comfyui:$!" >> "${PIDS_FILE}"

    if wait_for_port 8188 "ComfyUI" 60; then
        log_success "ComfyUI started"
    else
        log_error "ComfyUI failed to start"
        tail -20 "${LOGS_DIR}/comfyui/comfyui.log"
        return 1
    fi

    # 3. API
    log_info "Starting API..."
    cd "${APP_ROOT}"
    # IMPORTANT: Only add /app to PYTHONPATH, not /app/packages/shared/src
    # Adding src directly causes types.py to shadow stdlib types module
    export PYTHONPATH="${APP_ROOT}"
    nohup python -m uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 \
        > "${LOGS_DIR}/api/api.log" 2>&1 &
    echo "api:$!" >> "${PIDS_FILE}"

    if wait_for_port 8000 "API" 30; then
        log_success "API started"
    else
        log_error "API failed to start"
        tail -20 "${LOGS_DIR}/api/api.log"
        return 1
    fi

    # 4. Worker
    log_info "Starting Worker..."
    cd "${APP_ROOT}"
    # Use same PYTHONPATH as API
    export PYTHONPATH="${APP_ROOT}"
    nohup python -m apps.worker.src.main \
        > "${LOGS_DIR}/worker/worker.log" 2>&1 &
    echo "worker:$!" >> "${PIDS_FILE}"
    sleep 3

    if pgrep -f "apps.worker" > /dev/null; then
        log_success "Worker started"
    else
        log_error "Worker failed to start"
        tail -20 "${LOGS_DIR}/worker/worker.log"
        return 1
    fi

    # 5. Web (optional - may already be running via npm)
    log_info "Starting Web..."
    cd "${APP_ROOT}/apps/web"
    if [ -d "node_modules" ]; then
        nohup npm run dev -- --host 0.0.0.0 --port 3000 \
            > "${LOGS_DIR}/web/web.log" 2>&1 &
        echo "web:$!" >> "${PIDS_FILE}"

        if wait_for_port 3000 "Web" 30; then
            log_success "Web started"
        else
            log_warn "Web may not have started - check logs"
        fi
    else
        log_warn "Web node_modules not found - skipping"
    fi

    log_success "All services started"
}

###############################################################################
# Phase 7: Health Checks
###############################################################################

run_health_checks() {
    log_section "Phase 7: Health Checks"

    local all_healthy=true

    # Redis
    if redis-cli ping 2>/dev/null | grep -q PONG; then
        log_success "Redis: HEALTHY"
    else
        log_error "Redis: UNHEALTHY"
        all_healthy=false
    fi

    # API
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        log_success "API: HEALTHY"
    else
        log_error "API: UNHEALTHY"
        all_healthy=false
    fi

    # ComfyUI
    if curl -sf http://localhost:8188/system_stats > /dev/null 2>&1; then
        log_success "ComfyUI: HEALTHY"
    else
        log_error "ComfyUI: UNHEALTHY"
        all_healthy=false
    fi

    # Web
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        log_success "Web: HEALTHY"
    else
        log_warn "Web: NOT RESPONDING (may be optional)"
    fi

    if [ "$all_healthy" = true ]; then
        log_success "All critical services healthy"
        return 0
    else
        log_error "Some services unhealthy"
        return 1
    fi
}

###############################################################################
# Phase 8: E2E Smoke Test
###############################################################################

run_e2e_smoke_test() {
    log_section "Phase 8: E2E Smoke Test"

    local test_passed=true

    # Test 1: List characters
    log_info "Test 1: GET /api/characters"
    if curl -sf http://localhost:8000/api/characters > /dev/null; then
        log_success "Characters endpoint OK"
    else
        log_error "Characters endpoint FAILED"
        test_passed=false
    fi

    # Test 2: Create test character
    log_info "Test 2: POST /api/characters (create test)"
    local create_response=$(curl -sf -X POST http://localhost:8000/api/characters \
        -H "Content-Type: application/json" \
        -d '{"name": "smoke_test_char", "description": "E2E smoke test"}' 2>/dev/null)

    if echo "$create_response" | grep -q "id"; then
        local char_id=$(echo "$create_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
        log_success "Created test character: $char_id"
    else
        log_warn "Could not create test character (may already exist)"
    fi

    # Test 3: Check training endpoint
    log_info "Test 3: GET /api/training"
    if curl -sf http://localhost:8000/api/training > /dev/null; then
        log_success "Training endpoint OK"
    else
        log_error "Training endpoint FAILED"
        test_passed=false
    fi

    # Test 4: Check generation endpoint
    log_info "Test 4: GET /api/generation"
    if curl -sf http://localhost:8000/api/generation > /dev/null; then
        log_success "Generation endpoint OK"
    else
        log_error "Generation endpoint FAILED"
        test_passed=false
    fi

    # Test 5: Check ComfyUI object_info (validates node availability)
    log_info "Test 5: ComfyUI object_info"
    if curl -sf http://localhost:8188/object_info > /dev/null; then
        log_success "ComfyUI nodes available"
    else
        log_error "ComfyUI nodes FAILED"
        test_passed=false
    fi

    # Test 6: Verify AI-Toolkit is callable
    log_info "Test 6: AI-Toolkit import test"
    if "${AITOOLKIT_VENV}/bin/python" -c "from toolkit.job import run_job; print('OK')" 2>/dev/null; then
        log_success "AI-Toolkit callable"
    else
        log_error "AI-Toolkit NOT callable"
        test_passed=false
    fi

    if [ "$test_passed" = true ]; then
        log_success "E2E SMOKE TEST PASSED"
        return 0
    else
        log_error "E2E SMOKE TEST FAILED"
        return 1
    fi
}

###############################################################################
# Main Execution
###############################################################################

main() {
    echo ""
    echo "============================================================================="
    echo "  ISENGARD BOOTSTRAP v2"
    echo "  $(date)"
    echo "============================================================================="
    echo ""

    local skip_e2e=false
    local restart_only=false

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --skip-e2e)
                skip_e2e=true
                ;;
            --restart-only)
                restart_only=true
                ;;
        esac
    done

    # Always do environment setup
    setup_environment

    if [ "$restart_only" = false ]; then
        setup_aitoolkit
        patch_aitoolkit_plugin
        setup_model_symlinks
    fi

    stop_services
    start_services
    run_health_checks

    if [ "$skip_e2e" = false ]; then
        run_e2e_smoke_test
    else
        log_warn "E2E smoke test skipped (--skip-e2e)"
    fi

    echo ""
    log_section "Bootstrap Complete"
    echo ""
    echo "Services running:"
    echo "  - API:     http://localhost:8000"
    echo "  - ComfyUI: http://localhost:8188"
    echo "  - Web:     http://localhost:3000"
    echo ""
    echo "Logs:"
    echo "  - API:     ${LOGS_DIR}/api/api.log"
    echo "  - Worker:  ${LOGS_DIR}/worker/worker.log"
    echo "  - ComfyUI: ${LOGS_DIR}/comfyui/comfyui.log"
    echo "  - Web:     ${LOGS_DIR}/web/web.log"
    echo ""
    echo "Quick commands:"
    echo "  tail -f ${LOGS_DIR}/api/api.log"
    echo "  tail -f ${LOGS_DIR}/worker/worker.log"
    echo ""
}

# Run main
main "$@"
