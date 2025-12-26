"""
Isengard API - Client Logs Endpoint

Receives and persists logs from frontend clients.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from packages.shared.src.logging import get_logger, get_correlation_id

router = APIRouter()
logger = get_logger("api.routes.logs")


class ClientLogEntry(BaseModel):
    """Single log entry from client."""
    timestamp: str = Field(..., description="ISO 8601 timestamp from client")
    level: str = Field(..., description="Log level: DEBUG, INFO, WARNING, ERROR")
    message: str = Field(..., description="Log message")
    event: Optional[str] = Field(None, description="Event type (e.g., ui.button.click)")
    context: Optional[dict] = Field(None, description="Additional context data")


class ClientLogsRequest(BaseModel):
    """Batch of log entries from client."""
    entries: list[ClientLogEntry] = Field(..., description="Log entries to persist")


class ClientLogsResponse(BaseModel):
    """Response for client log submission."""
    received: int = Field(..., description="Number of entries received")
    correlation_id: str = Field(..., description="Server correlation ID")


@router.post("", response_model=ClientLogsResponse, status_code=201)
async def receive_client_logs(
    request: Request,
    body: ClientLogsRequest,
):
    """
    Receive and persist client-side logs.

    Frontend applications POST batches of log entries here for
    server-side persistence and analysis.
    """
    correlation_id = get_correlation_id() or "unknown"

    # Get client identifier if available
    user_agent = request.headers.get("User-Agent", "unknown")

    # Log receipt
    logger.info(
        f"Received {len(body.entries)} client log entries",
        extra={
            "event": "client.logs.received",
            "entry_count": len(body.entries),
            "user_agent": user_agent[:100] if user_agent else None,  # Truncate
        }
    )

    # Log each client entry with server context
    for entry in body.entries:
        level = entry.level.upper()
        log_method = getattr(logger, level.lower(), logger.info)

        extra = {
            "event": entry.event or "client.log",
            "client_timestamp": entry.timestamp,
            "source": "client",
        }

        if entry.context:
            extra.update(entry.context)

        log_method(
            f"[CLIENT] {entry.message}",
            extra=extra,
        )

    return ClientLogsResponse(
        received=len(body.entries),
        correlation_id=correlation_id,
    )
