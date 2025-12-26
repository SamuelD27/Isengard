"""
Isengard Redis Client Module

Provides Redis client and utilities for:
- Job queue (Redis Streams)
- Job state persistence
- Progress event streaming
- Consumer groups for workers

Redis Stream Names:
- isengard:jobs:training    - Training job submissions
- isengard:jobs:generation  - Generation job submissions
- isengard:progress:{job_id} - Progress updates (ephemeral)

Redis Hash Keys:
- isengard:jobs:index       - Job ID → status mapping
- isengard:jobs:data:{id}   - Full job data JSON
- isengard:characters:{id}  - Character data JSON
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import Redis

from .config import get_global_config
from .logging import get_logger

logger = get_logger("shared.redis")

# Stream and key names
STREAM_TRAINING = "isengard:jobs:training"
STREAM_GENERATION = "isengard:jobs:generation"
STREAM_PROGRESS_PREFIX = "isengard:progress:"
HASH_JOBS_INDEX = "isengard:jobs:index"
HASH_JOBS_DATA_PREFIX = "isengard:jobs:data:"
HASH_CHARACTERS_PREFIX = "isengard:characters:"
CONSUMER_GROUP = "workers"

# Singleton client
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        config = get_global_config()
        _redis_client = redis.from_url(
            config.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis client created", extra={
            "event": "redis.connect",
            "url": config.redis_url.replace(config.redis_url.split("@")[-1] if "@" in config.redis_url else "", "***"),
        })
    return _redis_client


async def close_redis() -> None:
    """Close Redis client connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis client closed", extra={"event": "redis.disconnect"})


async def ensure_consumer_groups() -> None:
    """Create consumer groups for job streams if they don't exist."""
    r = await get_redis()

    for stream in [STREAM_TRAINING, STREAM_GENERATION]:
        try:
            # Try to create the group, ignore if exists
            await r.xgroup_create(stream, CONSUMER_GROUP, id="0", mkstream=True)
            logger.info(f"Created consumer group for {stream}", extra={
                "event": "redis.group.created",
                "stream": stream,
                "group": CONSUMER_GROUP,
            })
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists, that's fine
                pass
            else:
                raise


# =============================================================================
# Job Queue Operations (Redis Streams)
# =============================================================================

async def submit_job(
    stream: str,
    job_id: str,
    job_type: str,
    payload: dict,
    correlation_id: str | None = None,
) -> str:
    """
    Submit a job to the queue (XADD).

    Args:
        stream: Stream name (STREAM_TRAINING or STREAM_GENERATION)
        job_id: Unique job ID
        job_type: Job type (training or generation)
        payload: Job payload as dict
        correlation_id: Optional correlation ID for tracing

    Returns:
        Redis message ID
    """
    r = await get_redis()

    message = {
        "id": job_id,
        "type": job_type,
        "correlation_id": correlation_id or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload": json.dumps(payload),
    }

    message_id = await r.xadd(stream, message)

    logger.info(f"Job submitted to queue", extra={
        "event": "job.queued",
        "job_id": job_id,
        "stream": stream,
        "message_id": message_id,
    })

    return message_id


async def consume_jobs(
    stream: str,
    consumer_name: str,
    count: int = 1,
    block_ms: int = 5000,
) -> list[tuple[str, dict]]:
    """
    Consume jobs from queue (XREADGROUP).

    Args:
        stream: Stream name
        consumer_name: Unique consumer identifier
        count: Max messages to read
        block_ms: Block timeout in milliseconds

    Returns:
        List of (message_id, data) tuples
    """
    r = await get_redis()

    try:
        messages = await r.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=consumer_name,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
    except redis.ResponseError as e:
        if "NOGROUP" in str(e):
            await ensure_consumer_groups()
            return []
        raise

    if not messages:
        return []

    result = []
    for stream_name, entries in messages:
        for entry_id, data in entries:
            # Parse payload back to dict
            if "payload" in data:
                data["payload"] = json.loads(data["payload"])
            result.append((entry_id, data))

    return result


async def acknowledge_job(stream: str, message_id: str) -> None:
    """Acknowledge job completion (XACK)."""
    r = await get_redis()
    await r.xack(stream, CONSUMER_GROUP, message_id)
    logger.debug(f"Job acknowledged", extra={
        "event": "job.acked",
        "stream": stream,
        "message_id": message_id,
    })


# =============================================================================
# Job State Persistence
# =============================================================================

async def save_job(job_id: str, job_data: dict) -> None:
    """Save job data to Redis."""
    r = await get_redis()
    key = f"{HASH_JOBS_DATA_PREFIX}{job_id}"
    await r.set(key, json.dumps(job_data))
    await r.hset(HASH_JOBS_INDEX, job_id, job_data.get("status", "unknown"))


async def get_job(job_id: str) -> dict | None:
    """Get job data from Redis."""
    r = await get_redis()
    key = f"{HASH_JOBS_DATA_PREFIX}{job_id}"
    data = await r.get(key)
    if data:
        return json.loads(data)
    return None


async def update_job_status(job_id: str, status: str, **extra_fields) -> None:
    """Update job status and optional extra fields."""
    r = await get_redis()

    # Get current data
    job_data = await get_job(job_id)
    if not job_data:
        return

    # Update fields
    job_data["status"] = status
    job_data.update(extra_fields)

    # Save back
    await save_job(job_id, job_data)


async def list_jobs(job_type: str | None = None, limit: int = 100) -> list[dict]:
    """List jobs from index."""
    r = await get_redis()

    # Get all job IDs from index
    index = await r.hgetall(HASH_JOBS_INDEX)

    jobs = []
    for job_id in list(index.keys())[:limit]:
        job_data = await get_job(job_id)
        if job_data:
            if job_type is None or job_data.get("type") == job_type:
                jobs.append(job_data)

    return sorted(jobs, key=lambda x: x.get("created_at", ""), reverse=True)


# =============================================================================
# Progress Events (Redis Streams)
# =============================================================================

async def publish_progress(
    job_id: str,
    status: str,
    progress: float,
    message: str,
    correlation_id: str | None = None,
    **extra,
) -> str:
    """
    Publish progress event to job-specific stream.

    Args:
        job_id: Job ID
        status: Current status (pending, running, completed, failed)
        progress: Progress percentage (0-100)
        message: Human-readable progress message
        correlation_id: Optional correlation ID
        **extra: Additional fields (current_step, total_steps, etc.)

    Returns:
        Redis message ID
    """
    r = await get_redis()
    stream = f"{STREAM_PROGRESS_PREFIX}{job_id}"

    event = {
        "job_id": job_id,
        "correlation_id": correlation_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "progress": str(progress),
        "message": message,
        **{k: str(v) for k, v in extra.items()},
    }

    message_id = await r.xadd(stream, event, maxlen=100)  # Keep last 100 events
    return message_id


async def get_latest_progress(job_id: str) -> dict | None:
    """Get latest progress event for a job."""
    r = await get_redis()
    stream = f"{STREAM_PROGRESS_PREFIX}{job_id}"

    # Get last entry
    entries = await r.xrevrange(stream, count=1)
    if not entries:
        return None

    _, data = entries[0]
    # Convert numeric strings back to numbers
    if "progress" in data:
        data["progress"] = float(data["progress"])
    if "current_step" in data:
        data["current_step"] = int(data["current_step"])
    if "total_steps" in data:
        data["total_steps"] = int(data["total_steps"])

    return data


async def stream_progress(
    job_id: str,
    last_id: str = "0",
) -> AsyncGenerator[dict, None]:
    """
    Stream progress events for a job.

    Yields progress events as they arrive.
    """
    r = await get_redis()
    stream = f"{STREAM_PROGRESS_PREFIX}{job_id}"

    while True:
        try:
            entries = await r.xread({stream: last_id}, count=10, block=1000)
            if entries:
                for stream_name, messages in entries:
                    for message_id, data in messages:
                        last_id = message_id
                        # Convert numeric strings
                        if "progress" in data:
                            data["progress"] = float(data["progress"])
                        yield data

                        # Check if job completed
                        if data.get("status") in ("completed", "failed", "cancelled"):
                            return
        except asyncio.CancelledError:
            return


# =============================================================================
# Character Persistence
# =============================================================================

async def save_character(char_id: str, char_data: dict) -> None:
    """Save character data to Redis."""
    r = await get_redis()
    key = f"{HASH_CHARACTERS_PREFIX}{char_id}"
    await r.set(key, json.dumps(char_data))


async def get_character(char_id: str) -> dict | None:
    """Get character data from Redis."""
    r = await get_redis()
    key = f"{HASH_CHARACTERS_PREFIX}{char_id}"
    data = await r.get(key)
    if data:
        return json.loads(data)
    return None


async def delete_character(char_id: str) -> None:
    """Delete character from Redis."""
    r = await get_redis()
    key = f"{HASH_CHARACTERS_PREFIX}{char_id}"
    await r.delete(key)


async def list_characters() -> list[dict]:
    """List all characters."""
    r = await get_redis()

    # Scan for character keys
    characters = []
    async for key in r.scan_iter(f"{HASH_CHARACTERS_PREFIX}*"):
        data = await r.get(key)
        if data:
            characters.append(json.loads(data))

    return sorted(characters, key=lambda x: x.get("created_at", ""), reverse=True)


# =============================================================================
# Health Check
# =============================================================================

async def check_redis_health() -> bool:
    """Check if Redis is healthy."""
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}", extra={
            "event": "redis.health.failed",
            "error": str(e),
        })
        return False
