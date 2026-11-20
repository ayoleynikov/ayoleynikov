"""Celery application — full Pulse queue set, retry defaults, routing."""

from __future__ import annotations

from celery import Celery

from pulse.config import get_settings
from pulse.workers.queues import ALL_QUEUES, QueueName, WORKER_QUEUES
from pulse.workers.retry import DEFAULT_RETRY_POLICY

settings = get_settings()

celery_app = Celery(
    "pulse",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "pulse.workers.tasks",
        "pulse.workers.stub_tasks",
        "pulse.workers.ingestion_tasks",
        "pulse.workers.analytics_tasks",
    ],
)

# Explicit queue declarations for Redis broker.
task_queues = {name: {"exchange": name, "routing_key": name} for name in ALL_QUEUES}

task_routes = {
    "pulse.workers.tasks.poll_rss_feed": {"queue": QueueName.SOURCE_POLL.value},
    "pulse.workers.tasks.poll_configured_rss_feeds": {"queue": QueueName.SOURCE_POLL.value},
    "pulse.workers.tasks.discover_sources": {"queue": QueueName.SOURCE_DISCOVERY.value},
    "pulse.workers.tasks.fetch_source_item": {"queue": QueueName.SOURCE_FETCH.value},
    "pulse.workers.tasks.refuse_stream_on_celery": {"queue": QueueName.SOURCE_STREAM.value},
    "pulse.workers.ingestion_tasks.normalize_batch": {"queue": QueueName.INGESTION_NORMALIZE.value},
    "pulse.workers.ingestion_tasks.dedupe_batch": {"queue": QueueName.INGESTION_DEDUPE.value},
    "pulse.workers.ingestion_tasks.match_brands": {"queue": QueueName.MATCHING_BRAND.value},
    "pulse.workers.ingestion_tasks.run_pipeline": {"queue": QueueName.INGESTION_NORMALIZE.value},
    "pulse.workers.analytics_tasks.search_gdelt": {"queue": QueueName.SOURCE_FETCH.value},
    "pulse.workers.analytics_tasks.sink_to_clickhouse": {"queue": QueueName.ANALYTICS_AGGREGATE.value},
    "pulse.workers.stub_tasks.run_ai_processing": {"queue": QueueName.PROCESSING_AI.value},
    "pulse.workers.stub_tasks.aggregate_analytics": {"queue": QueueName.ANALYTICS_AGGREGATE.value},
    "pulse.workers.stub_tasks.dispatch_alerts": {"queue": QueueName.ALERTS_DISPATCH.value},
    "pulse.workers.stub_tasks.maintenance_cleanup": {"queue": QueueName.MAINTENANCE_CLEANUP.value},
    "pulse.workers.tasks.flaky_demo_task": {"queue": QueueName.MAINTENANCE_CLEANUP.value},
}

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue=QueueName.SOURCE_POLL.value,
    task_queues=task_queues,
    task_routes=task_routes,
    task_annotations={
        "*": {
            "max_retries": DEFAULT_RETRY_POLICY.max_retries,
            "retry_backoff": True,
            "retry_backoff_max": int(DEFAULT_RETRY_POLICY.max_delay_seconds),
            "retry_jitter": DEFAULT_RETRY_POLICY.jitter,
        }
    },
    beat_schedule={
        "poll-rss-feeds": {
            "task": "pulse.workers.tasks.poll_configured_rss_feeds",
            "schedule": 300.0,
            "options": {"queue": QueueName.SOURCE_POLL.value},
        },
        "maintenance-cleanup-stub": {
            "task": "pulse.workers.stub_tasks.maintenance_cleanup",
            "schedule": 3600.0,
            "options": {"queue": QueueName.MAINTENANCE_CLEANUP.value},
        },
    },
)

# Exported for compose / docs.
DEFAULT_WORKER_QUEUE_CSV = ",".join(WORKER_QUEUES)
