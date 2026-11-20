"""Celery tasks for bounded source jobs (RSS poll, discovery/fetch stubs, retry demo)."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from sqlalchemy import select

from pulse.config import get_settings
from pulse.db.session import get_session_factory, reset_engine
from pulse.ingestion.store import poll_rss_feed
from pulse.logging import configure_logging, get_logger
from pulse.models.feed_source import FeedSource
from pulse.workers.base_task import PulseTask
from pulse.workers.boundaries import STREAM_REFUSAL_MESSAGE, assert_not_asyncio_workload
from pulse.workers.celery_app import celery_app
from pulse.workers.idempotency import IdempotencyStore
from pulse.workers.queues import QueueName
from pulse.workers.retry import PermanentTaskError, TransientTaskError

logger = get_logger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.tasks.poll_rss_feed",
)
def poll_rss_feed_task(
    self: PulseTask,
    feed_url: str,
    project_id: str | None = None,
    source_key: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Poll a single public RSS/Atom feed and persist mentions."""
    configure_logging(get_settings())
    store = IdempotencyStore()
    key = idempotency_key or store.make_key(
        self.name or "poll_rss_feed",
        feed_url,
        project_id or "",
        source_key or "",
    )
    cached = store.get_completed(key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    if not store.begin(key):
        return {"status": "duplicate_inflight", "feed_url": feed_url, "idempotency_key": key}

    try:
        result = _run_async(_poll_one(feed_url, project_id, source_key))
        if result.get("error"):
            err = str(result["error"])
            store.release(key)
            if err.startswith("transient:") or err.startswith("rate_limit:"):
                raise TransientTaskError(err)
            raise PermanentTaskError(err)
        result["idempotency_key"] = key
        result["status"] = "ok"
        store.complete(key, result)
        return result
    except (TransientTaskError, PermanentTaskError):
        store.release(key)
        raise
    except Exception as exc:  # noqa: BLE001
        store.release(key)
        raise TransientTaskError(str(exc)) from exc


async def _poll_one(
    feed_url: str,
    project_id: str | None,
    source_key: str | None,
) -> dict[str, Any]:
    reset_engine()
    factory = get_session_factory()
    async with factory() as session:
        outcome = await poll_rss_feed(
            session,
            feed_url=feed_url,
            project_id=UUID(project_id) if project_id else None,
            source_key=source_key,
        )
        return outcome.model_dump()


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.tasks.poll_configured_rss_feeds",
)
def poll_configured_rss_feeds(self: PulseTask) -> dict[str, Any]:
    """Poll enabled ``feed_sources`` rows plus optional ``PULSE_RSS_FEEDS`` env list."""
    configure_logging(get_settings())
    return _run_async(_poll_configured())


async def _poll_configured() -> dict[str, Any]:
    reset_engine()
    factory = get_session_factory()
    results: list[dict[str, Any]] = []
    errors = 0

    async with factory() as session:
        rows = (
            await session.execute(select(FeedSource).where(FeedSource.enabled.is_(True)))
        ).scalars().all()
        for row in rows:
            outcome = await poll_rss_feed(
                session,
                feed_url=row.feed_url,
                project_id=row.project_id,
                source_key=None,
            )
            payload = outcome.model_dump()
            results.append(payload)
            if outcome.error:
                errors += 1

    env_feeds = os.environ.get("PULSE_RSS_FEEDS", "").strip()
    if env_feeds:
        async with factory() as session:
            for url in [u.strip() for u in env_feeds.split(",") if u.strip()]:
                outcome = await poll_rss_feed(session, feed_url=url)
                results.append(outcome.model_dump())
                if outcome.error:
                    errors += 1

    if not results:
        logger.warning("rss_poll_no_feeds_configured")
        return {"polled": 0, "errors": 0, "results": [], "warning": "no feeds configured"}

    return {"polled": len(results), "errors": errors, "results": results, "status": "ok"}


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.tasks.discover_sources",
)
def discover_sources(self: PulseTask, project_id: str | None = None) -> dict[str, Any]:
    """Stub: source discovery (later phases)."""
    return {
        "status": "not_implemented",
        "stage": "source.discovery",
        "phase": "phase-4",
        "project_id": project_id,
    }


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.tasks.fetch_source_item",
)
def fetch_source_item(
    self: PulseTask,
    source_url: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Stub: bounded fetch of a single item URL."""
    return {
        "status": "not_implemented",
        "stage": "source.fetch",
        "phase": "phase-4",
        "source_url": source_url,
        "idempotency_key": idempotency_key,
    }


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.tasks.refuse_stream_on_celery",
)
def refuse_stream_on_celery(self: PulseTask) -> dict[str, Any]:
    """Enforce boundary: streaming is asyncio-only."""
    assert_not_asyncio_workload("bluesky.jetstream")
    raise PermanentTaskError(STREAM_REFUSAL_MESSAGE)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.tasks.flaky_demo_task",
    max_retries=3,
)
def flaky_demo_task(
    self: PulseTask,
    fail_times: int = 2,
    *,
    _attempts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Test helper: fails ``fail_times`` then succeeds (retry engine smoke).

    For unit tests, prefer calling the retry helpers directly; this task is for
    integration when a broker is available.
    """
    # Celery redeliveries don't keep process-local state; use request.retries.
    if self.request.retries < fail_times:
        raise TransientTaskError(f"induced failure attempt={self.request.retries}")
    return {"status": "ok", "retries": self.request.retries}
