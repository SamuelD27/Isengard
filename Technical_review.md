# Comprehensive Technical Design for Isengard's LoRA Monitoring System

Flux.1-dev's 12B-parameter DiT architecture requires monitoring 57 transformer blocks with **3,072-dimensional hidden states**, where identity learning primarily occurs in single-stream blocks 19-29. This report provides first-principles technical foundations for building ground-truth observability into LoRA training and generation, specifically optimized for raw JSONL logging consumed by a single expert user and Claude Code.

## Flux.1-dev architecture fundamentals shape monitoring requirements

Flux.1-dev uses a **hybrid Diffusion Transformer** with two distinct block types that must be monitored differently. The architecture consists of **19 double-stream MM-DiT blocks** (indices 0-18) that maintain separate weight streams for image and text tokens with joint attention, followed by **38 single-stream blocks** (indices 19-56) that process concatenated tokens with shared weights and parallel attention+FFN computation.

The core dimensions define what to monitor:
- Hidden size: **3,072** (24 attention heads × 128 dimensions per head)
- Latent channels: **16** (packed from VAE's 4×4 spatial patches)
- T5 conditioning: **4,096** dimensions projected to 3,072
- RoPE positional encoding: 3D (16 time dims, 56×2 height, 56×2 width)

**LoRA application points for identity training** should target these specific parameter names in diffusers:
```
transformer_blocks.{i}.attn.to_q      # Image query projection
transformer_blocks.{i}.attn.to_k      # Image key projection  
transformer_blocks.{i}.attn.to_v      # Image value projection
transformer_blocks.{i}.attn.to_out.0  # Image output projection
single_transformer_blocks.{i}.attn.*  # Single-stream attention
```

For identity LoRAs, **blocks 19-29 are most critical** for subject/content learning, while blocks 30-56 control style. This creates a natural monitoring hierarchy: double-stream blocks (semantic mapping), early single-stream (identity), late single-stream (style).

## Training dynamics reveal what metrics actually matter

The LoRA forward pass computes `h = W₀x + (α/r) × B × A × x`, where B is initialized to zeros ensuring no initial perturbation. The critical insight: **A's gradients are ineffective early in training** because they're multiplied by zero-initialized B. This means monitoring the up-projection (B) weight norms is essential for detecting actual learning onset.

### Loss function specifics for Flux

Flux uses **rectified flow training** with velocity prediction, not DDPM noise prediction:
- Interpolation: `x_t = (1-t) × noise + t × clean_image` 
- Training objective: Predict velocity `v = x₁ - x₀`
- Time range: t ∈ [0,1] where t=0 is noise, t=1 is clean

The default **logit-normal timestep sampling** `t = σ(N(μ,σ²))` focuses training on middle timesteps. For identity learning, timesteps 200-500 are most important—this is where facial details are learned. Log per-timestep-bucket losses to detect imbalance.

Healthy loss values for Flux LoRA training:
| Stage | Expected Loss | Warning Signs |
|-------|--------------|---------------|
| Early (0-100 steps) | 0.2-0.5 | >0.5 suggests LR too low |
| Mid training | 0.05-0.15 | Oscillation suggests LR too high |
| Converged | 0.02-0.08 | <0.01 suggests overfitting |

### Gradient flow through LoRA layers

The gradients for LoRA matrices during backprop are:
```python
grad_B = grad_output.T @ (A @ x)    # Shape: (d_out, r)
grad_A = B.T @ grad_output @ x.T    # Shape: (r, d_in)
```

Healthy gradient magnitude ranges:
- **lora_down (A)**: 0.001-0.1 (vanishing if <1e-6, exploding if >1.0)
- **lora_up (B)**: 0.0001-0.05 (vanishing if <1e-7, exploding if >0.5)
- **Total norm before clipping**: 0.1-10.0 (critical if >100 or NaN)

Log the ratio of first-layer to last-layer gradient norms—healthy training shows ratio within 10-100×, problematic training shows >1000× difference indicating vanishing gradients in early layers.

### Optimizer state monitoring

**Prodigy optimizer** (recommended for LoRA) tracks a `d` value representing estimated distance to optimum. This is the most important metric for adaptive LR monitoring:
- If d remains too small: increase d0 to 1e-5
- d_coef < 1.0 gives more conservative adaptation
- **Always log the d value per optimizer step**

For AdamW, track:
- `exp_avg` (momentum): Running mean of gradients
- `exp_avg_sq` (variance): Running mean of squared gradients  
- Effective update magnitude: `grad_norm × lr` (should be <0.1 per layer)

## LoRA weight evolution patterns indicate training health

Track three norms per LoRA layer:
```python
down_norm = module.lora_down.weight.norm()      # A matrix
up_norm = module.lora_up.weight.norm()          # B matrix  
product_norm = (up @ down).norm()               # Effective ΔW
```

Expected evolution:
| Phase | A (down) Norm | B (up) Norm | Product Norm |
|-------|--------------|-------------|--------------|
| Init | ~0.5-1.0 | 0 | 0 |
| Early | ~0.5-1.0 | 0.001-0.01 | ~0.001 |
| Mid | Stable | Growing | Growing |
| Converged | Stable | Stable | Stable |
| Overfit | Decreasing diversity | Large | Very large |

**Effective rank monitoring** reveals capacity utilization. Compute SVD of the product matrix:
```python
S = torch.linalg.svdvals(up @ down)
effective_rank = (S > S[0] * 0.01).sum()  # Should use most of allocated rank
dominant_ratio = S[0] / S.sum()           # Should be <0.8 for healthy training
```

Mode collapse manifests as: effective_rank << allocated_rank, dominant_ratio > 0.9, high correlation between different LoRA layers' weight products.

## Attention statistics track identity learning progress

For diffusion transformers, monitor attention entropy as a proxy for learning focus:
```python
attention_entropy = -(attn_weights * log(attn_weights + 1e-10)).sum(dim=-1).mean()
```

| Training Phase | Expected Entropy | Indication |
|---------------|------------------|------------|
| Early | >3.0 | Unfocused, learning basic patterns |
| Mid | 2.0-3.0 | Learning identity-specific patterns |
| Converged | 1.5-2.5 | Focused on relevant tokens |
| Overfit | <1.0 | Over-specialized, memorizing training data |

For identity LoRAs, track **trigger word attention strength**: how strongly image tokens attend to the trigger word position in cross-attention. This should increase during training then plateau—continued increase suggests overfitting.

## Failure modes have distinct signatures in raw logs

### NaN/Inf propagation detection

NaN typically originates from (in order of likelihood):
1. Gradient computation (backprop through attention softmax)
2. Loss calculation (log of zero, division by zero)
3. Activation overflow (large attention scores before softmax)
4. Accumulated weight updates

**Early detection requires checking after every forward pass:**
```python
def nan_check_hook(module, input, output):
    if not torch.isfinite(output).all():
        return {"layer": module.__class__.__name__, "has_nan": True, "has_inf": True}
```

Log `nan_count` and `inf_count` per step. Any non-zero value requires immediate attention.

### Gradient explosion signatures

Sequential warning pattern in logs:
1. Gradient norm >10× typical value
2. Loss spikes
3. Gradient norm >100× typical value
4. Loss becomes NaN

Detection threshold: if `total_grad_norm > 10.0` for 3+ consecutive steps, explosion is imminent. Automatic response should reduce LR or enable gradient clipping.

### Training divergence detection

Divergence manifests as:
- Loss increasing consistently for 50+ steps
- Loss variance *increasing* over time (opposite of healthy convergence)
- Generated samples degrading in quality

Track rolling statistics:
```python
loss_ema = 0.99 * loss_ema + 0.01 * current_loss
loss_variance_rolling = std(last_100_losses)
```

### VRAM exhaustion patterns

Warning signs in logs:
- Training hangs with no progress messages
- Gradual slowdown in step timing
- PyTorch CUDA OOM warning logs
- `torch.cuda.memory_stats()` showing `num_alloc_retries` increasing

Log memory stats per step:
```python
{
    "allocated_bytes": torch.cuda.memory_allocated(),
    "reserved_bytes": torch.cuda.memory_reserved(),
    "max_allocated_bytes": torch.cuda.max_memory_allocated(),
    "num_alloc_retries": torch.cuda.memory_stats()["num_alloc_retries"],
    "num_ooms": torch.cuda.memory_stats()["num_ooms"]
}
```

## Generation-time monitoring reveals training quality issues

### LoRA strength interaction effects

| Strength | Effect | Quality Indicator |
|----------|--------|-------------------|
| <0.5 | Weak effect | Trigger words don't activate, high seed variance |
| 0.7-1.0 | Standard | Consistent identity, good prompt adherence |
| 1.0-1.3 | Strong | Better identity lock, may reduce prompt flexibility |
| >1.3 | Overdriven | Color oversaturation, training data leakage |

**Log effective scale**: `lora_strength × (alpha / rank)` to compare across different LoRA configurations.

### CFG interaction with LoRA quality

Flux.1-dev is guidance-distilled with default CFG 3.5. With LoRAs:
- **CFG 2.5-3.5**: Best balance for identity preservation
- **CFG 3.5-7.0**: Stronger prompt following but may amplify LoRA artifacts
- **CFG >7.0**: Risk of oversaturation, avoid with LoRAs

Log CFG alongside generation quality metrics to correlate.

### Sampler-specific LoRA behavior

**Most forgiving samplers** (mask training issues):
1. Euler - stable, predictable baseline
2. DDIM - deterministic, good for reproducible testing
3. DPM++ 2M Karras - balanced quality/speed

**Least forgiving samplers** (expose training problems):
1. DPM++ SDE - highlights artifacts
2. Ancestral samplers (Euler a, DPM++ 2S a) - amplify variance

For quality assessment, generate with both forgiving (Euler) and unforgiving (DPM++ SDE) samplers and compare.

### Seed variance as training quality metric

Protocol: Generate 5-10 images with identical prompts but different seeds. Calculate:
```python
{
    "identity_consistency_score": face_embedding_similarity_mean,
    "structural_similarity_std": ssim_standard_deviation,
    "color_palette_variance": histogram_variance
}
```

**High seed variance** indicates undertrained LoRA (hasn't converged). **Low seed variance** indicates potential overfitting (limited generalization). Optimal: consistent identity core with natural variation in pose/expression.

## JSONL schema design for machine consumption

### Base schema (every log entry)
```json
{
  "ts": "2025-01-15T10:30:00.123456Z",
  "type": "training_step|sample|checkpoint|gpu|error",
  "step": 1000,
  "session": "uuid",
  "v": "1.0"
}
```

### Training step entry
```json
{
  "ts": "...",
  "type": "training_step",
  "step": 1000,
  "session": "...",
  "v": "1.0",
  "loss": 0.0234,
  "loss_ema": 0.0245,
  "lr": 0.0001,
  "grad": {
    "norm": 1.234,
    "clipped": false,
    "nan_count": 0,
    "vanishing_layers": 0,
    "exploding_layers": 0
  },
  "lora": {
    "down_norm_mean": 0.52,
    "up_norm_mean": 0.08,
    "product_norm_mean": 0.04,
    "effective_rank_mean": 28.5
  },
  "optimizer": {
    "prodigy_d": 0.00012
  },
  "timing": {
    "step_ms": 1234,
    "forward_ms": 890,
    "backward_ms": 299,
    "data_ms": 45
  }
}
```

### GPU metrics entry
```json
{
  "ts": "...",
  "type": "gpu",
  "step": 1000,
  "session": "...",
  "v": "1.0",
  "gpu_id": 0,
  "util_gpu": 95,
  "util_mem": 88,
  "mem_used_mb": 22400,
  "mem_total_mb": 24576,
  "temp_c": 72,
  "power_w": 285.5
}
```

### Generation log entry
```json
{
  "ts": "...",
  "type": "generation",
  "session": "...",
  "v": "1.0",
  "prompt": "...",
  "seed": 42,
  "steps": 35,
  "cfg": 3.5,
  "sampler": "euler",
  "loras": [{"name": "identity", "strength": 0.9, "rank": 32, "alpha": 32}],
  "output_path": "...",
  "timing": {
    "total_ms": 8500,
    "encode_ms": 120,
    "diffusion_ms": 7800,
    "vae_decode_ms": 580
  },
  "latent_stats": {
    "final_mean": -0.02,
    "final_std": 0.95,
    "final_range": 8.2
  }
}
```

## Implementation architecture for crash-resilient logging

### Core logging module pattern
```python
class CrashSafeJSONLLogger:
    def __init__(self, log_path):
        self.file = open(log_path, 'a', buffering=1)  # Line buffered
        
    def log(self, entry):
        line = json.dumps(entry, separators=(',', ':')) + '\n'
        self.file.write(line)
        self.file.flush()
        os.fsync(self.file.fileno())  # Force to disk
```

### PyTorch hook registration for comprehensive monitoring
```python
class TrainingMonitor:
    def __init__(self, model):
        self.activations = {}
        self.gradients = {}
        
        for name, module in model.named_modules():
            if 'lora' in name.lower():
                module.register_forward_hook(self._activation_hook(name))
                module.register_full_backward_hook(self._gradient_hook(name))
                
    def _activation_hook(self, name):
        def hook(module, input, output):
            self.activations[name] = {
                "mean": output.mean().item(),
                "std": output.std().item(),
                "has_nan": torch.isnan(output).any().item()
            }
        return hook
        
    def _gradient_hook(self, name):
        def hook(module, grad_in, grad_out):
            if grad_out[0] is not None:
                self.gradients[name] = {
                    "norm": grad_out[0].norm().item(),
                    "has_nan": torch.isnan(grad_out[0]).any().item()
                }
        return hook
```

### GPU monitoring thread
```python
import pynvml
import threading

class GPUMonitor(threading.Thread):
    def __init__(self, logger, interval=1.0):
        super().__init__(daemon=True)
        self.logger = logger
        self.interval = interval
        self.current_step = 0
        self._running = True
        
    def run(self):
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        
        while self._running:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            
            self.logger.log({
                "ts": datetime.utcnow().isoformat(),
                "type": "gpu",
                "step": self.current_step,
                "util_gpu": util.gpu,
                "mem_used_mb": mem.used // (1024**2),
                "temp_c": pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            })
            time.sleep(self.interval)
```

### Streaming reader for live monitoring
```python
def tail_jsonl(filepath, callback):
    """Follow log file like tail -f, parse each line as JSON."""
    with open(filepath, 'r') as f:
        f.seek(0, os.SEEK_END)  # Start at end
        while True:
            line = f.readline()
            if line:
                try:
                    entry = json.loads(line)
                    callback(entry)
                except json.JSONDecodeError:
                    pass  # Skip corrupted lines
            else:
                time.sleep(0.1)
```

## Critical thresholds summary for automated alerting

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Total grad norm | >10.0 | >100 or NaN | Reduce LR, enable clipping |
| Loss | Increasing 20+ steps | NaN or >10× initial | Stop training, check data |
| Loss variance | >30% of mean | >50% of mean | Reduce LR, check batch size |
| Effective rank | <50% allocated | <25% allocated | Check initialization, increase LR |
| Vanishing layers | >10% of total | >30% of total | Increase LR, check architecture |
| Step timing | >2× baseline | >5× baseline | Check VRAM, data loading |
| GPU memory | >95% | OOM | Enable checkpointing, reduce batch |
| Attention entropy | <1.0 | <0.5 | Reduce training steps (overfit) |

## Integration points with existing tools

**AI-Toolkit**: Hook into the Accelerate training loop by wrapping the `training_step` function. Config location: `config/examples/train_lora_flux_24gb.yaml`

**kohya-ss**: Use `--console_log_file` for stdout capture, add custom metrics via TensorBoard callback. Training loop in `train_network.py`.

**ComfyUI**: Use the execution API at `/prompt` endpoint, capture node execution times via forward hooks, stream progress via WebSocket connection.

**Process wrapping**: For any training process, use PTY-based capture to preserve terminal formatting while logging:
```python
import pty
master_fd, slave_fd = pty.openpty()
process = subprocess.Popen(cmd, stdout=slave_fd, stderr=slave_fd)
```

This design provides complete observability into LoRA training dynamics while maintaining crash resilience and enabling both real-time monitoring and post-hoc analysis by Claude Code. The JSONL format ensures machine parseability while remaining human-readable for debugging.