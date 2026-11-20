"""CLI entrypoint: poll one RSS feed without Celery.

Usage:
  pulse-poll-rss https://example.com/feed.xml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from pulse.config import get_settings
from pulse.db.session import get_session_factory, reset_engine
from pulse.ingestion.store import poll_rss_feed
from pulse.logging import configure_logging


async def _main(feed_url: str, project_id: str | None) -> int:
    settings = get_settings()
    configure_logging(settings)
    reset_engine()
    factory = get_session_factory(settings)
    async with factory() as session:
        outcome = await poll_rss_feed(
            session,
            feed_url=feed_url,
            project_id=UUID(project_id) if project_id else None,
        )
    print(json.dumps(outcome.model_dump(), default=str, indent=2))
    return 1 if outcome.error else 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Poll a public RSS/Atom feed into Pulse storage")
    parser.add_argument("feed_url", help="Public feed URL")
    parser.add_argument("--project-id", default=None, help="Optional project UUID")
    args = parser.parse_args(argv)
    code = asyncio.run(_main(args.feed_url, args.project_id))
    raise SystemExit(code)


if __name__ == "__main__":
    main(sys.argv[1:])
