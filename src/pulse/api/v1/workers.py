"""Worker / DLQ observability endpoints (Phase 4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pulse.workers.queues import ALL_QUEUES, ASYNCIO_ONLY_WORKLOADS, WORKER_QUEUES

router = APIRouter(prefix="/workers", tags=["workers"])


class QueueManifest(BaseModel):
    queues: list[str]
    worker_queues: list[str]
    dead_letter_queue: str = "dead_letter"
    asyncio_only: list[str] = Field(default_factory=list)
    note: str = (
        "Celery handles bounded jobs on the listed queues. "
        "WebSocket streams (e.g. Bluesky Jetstream) run via pulse-jetstream, not Celery."
    )


@router.get("/queues", response_model=QueueManifest)
async def list_queues() -> QueueManifest:
    return QueueManifest(
        queues=list(ALL_QUEUES),
        worker_queues=list(WORKER_QUEUES),
        asyncio_only=sorted(ASYNCIO_ONLY_WORKLOADS),
    )


class DLQListResponse(BaseModel):
    detail: str
    phase: str = "phase-4"
    hint: str = (
        "Query Postgres dead_letters (status=open) or use worker tooling. "
        "Listing via API with DB session lands with auth in a later phase."
    )
    example_query: dict[str, Any] = Field(
        default_factory=lambda: {
            "sql": "SELECT id, task_name, exception_message, retries, failed_at "
            "FROM dead_letters WHERE status='open' ORDER BY failed_at DESC LIMIT 100"
        }
    )


@router.get("/dead-letters", response_model=DLQListResponse)
async def dead_letters_hint() -> DLQListResponse:
    """Observability stub pointing at the durable DLQ table."""
    return DLQListResponse(detail="dead_letters table is the source of truth for exhausted failures")
