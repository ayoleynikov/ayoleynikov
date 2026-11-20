"""Celery tasks for RSS polling."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from sqlalchemy import select

from pulse.db.session import get_session_factory, reset_engine
from pulse.ingestion.store import poll_rss_feed
from pulse.logging import configure_logging, get_logger
from pulse.config import get_settings
from pulse.models.feed_source import FeedSource
from pulse.workers.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


@celery_app.task(name="pulse.workers.tasks.poll_rss_feed")
def poll_rss_feed_task(
    feed_url: str,
    project_id: str | None = None,
    source_key: str | None = None,
) -> dict[str, Any]:
    """Poll a single public RSS/Atom feed and persist mentions."""
    configure_logging(get_settings())
    return _run_async(_poll_one(feed_url, project_id, source_key))


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


@celery_app.task(name="pulse.workers.tasks.poll_configured_rss_feeds")
def poll_configured_rss_feeds() -> dict[str, Any]:
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

    # Comma-separated feed URLs for local/dev without DB rows.
    env_feeds = os.environ.get("PULSE_RSS_FEEDS", "").strip()
    if env_feeds:
        async with factory() as session:
            for url in [u.strip() for u in env_feeds.split(",") if u.strip()]:
                outcome = await poll_rss_feed(session, feed_url=url)
                results.append(outcome.model_dump())
                if outcome.error:
                    errors += 1

    if not results:
        # Explicit non-success when nothing is configured — not a silent empty win.
        logger.warning("rss_poll_no_feeds_configured")
        return {"polled": 0, "errors": 0, "results": [], "warning": "no feeds configured"}

    return {"polled": len(results), "errors": errors, "results": results}
