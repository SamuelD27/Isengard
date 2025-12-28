#!/usr/bin/env python3
"""
Debug Bundle Generator

Creates a comprehensive debug bundle for a training job including:
- Job metadata
- Event logs (JSONL)
- Service logs (last N lines)
- Sample images
- Environment snapshot (redacted)
- Directory tree

Usage:
    python scripts/debug_bundle.py <job_id> [--output <path>]

Example:
    python scripts/debug_bundle.py train-abc123
    python scripts/debug_bundle.py train-abc123 --output /tmp/debug.zip
"""

import argparse
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from packages.shared.src.config import get_global_config
from packages.shared.src.logging import get_job_log_path, get_job_samples_dir, redact_sensitive


def get_job_metadata(job_id: str) -> dict | None:
    """Get job metadata from Redis or file storage."""
    config = get_global_config()

    # Try to load from Redis
    try:
        import redis
        r = redis.from_url(config.redis_url)
        job_data = r.hgetall(f"isengard:job:{job_id}")
        if job_data:
            return {k.decode(): v.decode() for k, v in job_data.items()}
    except Exception:
        pass

    # Try to load from file-based storage
    job_file = config.volume_root / "jobs" / f"{job_id}.json"
    if job_file.exists():
        return json.loads(job_file.read_text())

    return None


def collect_service_logs(config, service: str, max_lines: int = 1000) -> str | None:
    """Collect last N lines from a service log."""
    log_path = config.log_dir / service / "latest" / f"{service}.log"
    if not log_path.exists():
        return None

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-max_lines:]
        return redact_sensitive("".join(lines))
    except Exception as e:
        return f"Error reading {service} log: {e}"


def create_debug_bundle(job_id: str, output_path: Path | None = None) -> Path:
    """Create a debug bundle for a job."""
    config = get_global_config()

    if output_path is None:
        bundles_dir = config.log_dir / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)
        output_path = bundles_dir / f"{job_id}_debug.zip"

    zip_buffer = io.BytesIO()
    bundle_contents = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Job metadata
        job_data = get_job_metadata(job_id)
        if job_data:
            safe_job_data = {
                k: v for k, v in job_data.items()
                if not any(s in k.lower() for s in ["token", "key", "secret", "password"])
            }
            job_json = json.dumps(safe_job_data, indent=2, default=str)
            zf.writestr(f"{job_id}/metadata.json", job_json)
            bundle_contents.append("metadata.json")
            print(f"  + metadata.json")
        else:
            print(f"  - metadata.json (not found)")

        # 2. Job log file
        log_path = get_job_log_path(job_id)
        if log_path and log_path.exists():
            log_content = log_path.read_text(encoding="utf-8")
            log_content = redact_sensitive(log_content)
            zf.writestr(f"{job_id}/events.jsonl", log_content)
            bundle_contents.append("events.jsonl")
            print(f"  + events.jsonl ({log_path.stat().st_size} bytes)")
        else:
            print(f"  - events.jsonl (not found)")

        # 3. Service logs
        for service in ["api", "worker", "plugins"]:
            log_content = collect_service_logs(config, service)
            if log_content:
                zf.writestr(f"{job_id}/service_logs/{service}.log", log_content)
                bundle_contents.append(f"service_logs/{service}.log")
                print(f"  + service_logs/{service}.log")
            else:
                print(f"  - service_logs/{service}.log (not found)")

        # 4. Sample images
        samples_dir = get_job_samples_dir(job_id)
        if samples_dir.exists():
            sample_files = list(samples_dir.glob("*.png"))
            for sample_file in sample_files:
                zf.write(sample_file, f"{job_id}/samples/{sample_file.name}")
                bundle_contents.append(f"samples/{sample_file.name}")
            if sample_files:
                print(f"  + samples/ ({len(sample_files)} images)")
        else:
            print(f"  - samples/ (not found)")

        # 5. Environment snapshot (heavily redacted)
        env_snapshot = {
            "ISENGARD_MODE": os.getenv("ISENGARD_MODE", "unknown"),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
            "USE_REDIS": os.getenv("USE_REDIS", "false"),
            "volume_root": str(config.volume_root),
            "log_dir": str(config.log_dir),
            "python_version": sys.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        zf.writestr(f"{job_id}/environment.json", json.dumps(env_snapshot, indent=2))
        bundle_contents.append("environment.json")
        print(f"  + environment.json")

        # 6. Directory tree
        tree_lines = [
            f"Debug Bundle for {job_id}",
            "=" * 40,
            "",
            "Contents:",
        ]
        for item in bundle_contents:
            tree_lines.append(f"  - {item}")
        tree_lines.extend([
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "How to use:",
            "  1. Open events.jsonl to find the first ERROR event",
            "  2. Check metadata.json for job configuration",
            "  3. Review service logs for context",
            "  4. Samples show training progress visually",
        ])
        zf.writestr(f"{job_id}/README.txt", "\n".join(tree_lines))

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(zip_buffer.getvalue())

    return output_path


def find_first_error(job_id: str) -> dict | None:
    """Find the first error in job logs."""
    log_path = get_job_log_path(job_id)
    if not log_path or not log_path.exists():
        return None

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("level") == "ERROR":
                        return {
                            "timestamp": entry.get("ts"),
                            "message": entry.get("msg"),
                            "event": entry.get("event"),
                            "error": entry.get("fields", {}).get("error"),
                            "error_type": entry.get("fields", {}).get("error_type"),
                        }
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return None


def main():
    parser = argparse.ArgumentParser(description="Create debug bundle for a training job")
    parser.add_argument("job_id", help="Job ID (e.g., train-abc123)")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for the ZIP file (default: logs/bundles/<job_id>_debug.zip)"
    )
    parser.add_argument(
        "--show-error", "-e",
        action="store_true",
        help="Show the first error from logs"
    )

    args = parser.parse_args()

    # Validate job ID format
    if not re.match(r"^[a-zA-Z0-9_-]+$", args.job_id):
        print(f"Error: Invalid job ID format: {args.job_id}", file=sys.stderr)
        sys.exit(1)

    print(f"\nCreating debug bundle for: {args.job_id}\n")

    # Show first error if requested
    if args.show_error:
        first_error = find_first_error(args.job_id)
        if first_error:
            print("First Error Found:")
            print(f"  Timestamp: {first_error.get('timestamp')}")
            print(f"  Event: {first_error.get('event')}")
            print(f"  Type: {first_error.get('error_type')}")
            print(f"  Message: {first_error.get('message')}")
            print(f"  Error: {first_error.get('error')}")
            print()
        else:
            print("No errors found in job logs.\n")

    try:
        output_path = create_debug_bundle(args.job_id, args.output)
        print(f"\nDebug bundle created: {output_path}")
        print(f"Size: {output_path.stat().st_size:,} bytes")
    except Exception as e:
        print(f"\nError creating debug bundle: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
