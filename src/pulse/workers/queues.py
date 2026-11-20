"""Canonical Celery queue names from the Pulse master spec."""

from __future__ import annotations

from enum import StrEnum


class QueueName(StrEnum):
    """Bounded-job queues. WebSocket streams use asyncio processes, not these queues."""

    SOURCE_DISCOVERY = "source.discovery"
    SOURCE_POLL = "source.poll"
    SOURCE_FETCH = "source.fetch"
    SOURCE_STREAM = "source.stream"  # stub only — real streaming is asyncio (pulse-jetstream)
    INGESTION_NORMALIZE = "ingestion.normalize"
    INGESTION_DEDUPE = "ingestion.dedupe"
    MATCHING_BRAND = "matching.brand"
    PROCESSING_AI = "processing.ai"
    ANALYTICS_AGGREGATE = "analytics.aggregate"
    ALERTS_DISPATCH = "alerts.dispatch"
    MAINTENANCE_CLEANUP = "maintenance.cleanup"
    DEAD_LETTER = "dead_letter"


ALL_QUEUES: tuple[str, ...] = tuple(q.value for q in QueueName)

# Queues a default Celery worker should consume (excludes dead_letter specialty).
WORKER_QUEUES: tuple[str, ...] = tuple(
    q.value for q in QueueName if q is not QueueName.DEAD_LETTER
)

# Documentation / enforcement: these must never run as long-lived Celery loops.
ASYNCIO_ONLY_WORKLOADS: frozenset[str] = frozenset(
    {
        "bluesky.jetstream",
        "websocket.stream",
    }
)
