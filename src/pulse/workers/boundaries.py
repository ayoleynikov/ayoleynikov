"""Enforce Celery (bounded jobs) vs asyncio (WebSocket streams) boundaries."""

from __future__ import annotations

from pulse.workers.queues import ASYNCIO_ONLY_WORKLOADS, QueueName
from pulse.workers.retry import PermanentTaskError


STREAM_REFUSAL_MESSAGE = (
    "WebSocket / Jetstream streaming must run as a dedicated asyncio process "
    "(pulse-jetstream), not as a Celery worker loop. "
    "Queue source.stream exists only as a routing stub."
)


def assert_not_asyncio_workload(workload: str) -> None:
    """Raise if a Celery task attempts an asyncio-only workload."""
    if workload in ASYNCIO_ONLY_WORKLOADS:
        raise PermanentTaskError(STREAM_REFUSAL_MESSAGE)


def refuse_celery_stream() -> dict[str, str]:
    """Return an explicit refusal payload for source.stream Celery invocations."""
    assert_not_asyncio_workload("bluesky.jetstream")
    # Unreachable if assert raises; kept for type clarity.
    return {"status": "refused", "queue": QueueName.SOURCE_STREAM.value}
