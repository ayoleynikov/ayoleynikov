"""Celery application for bounded source poll jobs."""

from __future__ import annotations

from celery import Celery

from pulse.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pulse",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["pulse.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_default_queue="source.poll",
    beat_schedule={
        # Minimal schedule placeholder — actual feeds come from DB / env at task run.
        "poll-rss-feeds": {
            "task": "pulse.workers.tasks.poll_configured_rss_feeds",
            "schedule": 300.0,
        },
    },
)
