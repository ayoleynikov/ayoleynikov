"""Long-running asyncio process for Bluesky Jetstream v2 consumption.

Usage:
  pulse-jetstream
  pulse-jetstream --region us-east-1
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Any

from pulse.config import get_settings
from pulse.connectors.bluesky.config import BlueskyJetstreamConfig, REGIONAL_ENDPOINTS
from pulse.connectors.bluesky.connector import BlueskyJetstreamConnector
from pulse.connectors.bluesky.consumer import JetstreamConsumer
from pulse.connectors.bluesky.parsing import (
    StreamDeleteEvent,
    StreamEvent,
    StreamPostEvent,
    StreamSkipEvent,
)
from pulse.connectors.types import CheckpointCursor
from pulse.db.session import get_session_factory, reset_engine
from pulse.ingestion.store import MentionStore
from pulse.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def _run(config: BlueskyJetstreamConfig) -> int:
    settings = get_settings()
    configure_logging(settings)
    reset_engine()
    factory = get_session_factory(settings)
    connector = BlueskyJetstreamConnector(config)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows / restricted environments
            pass

    async def load_checkpoint() -> CheckpointCursor | None:
        async with factory() as session:
            store = MentionStore(session)
            return await store.load_checkpoint(connector.name, connector.source_key())

    async def save_checkpoint(cursor: CheckpointCursor) -> None:
        async with factory() as session:
            store = MentionStore(session)
            await store.save_checkpoint(cursor, success=True, error=None)
            await session.commit()

    async def handle_event(event: StreamEvent) -> None:
        async with factory() as session:
            store = MentionStore(session)
            if isinstance(event, StreamPostEvent):
                await store.upsert_mentions([event.mention])
                await session.commit()
                logger.info(
                    "jetstream_post_stored",
                    extra={"external_id": event.mention.external_id},
                )
            elif isinstance(event, StreamDeleteEvent):
                deleted = await store.mark_deleted(
                    source=event.source,
                    external_id=event.external_id,
                )
                await session.commit()
                logger.info(
                    "jetstream_delete_applied",
                    extra={"external_id": event.external_id, "deleted": deleted},
                )
            elif isinstance(event, StreamSkipEvent):
                # Still acknowledged; checkpoint advanced by consumer after handler returns.
                logger.debug("jetstream_skip", extra={"reason": event.reason})
            # info events: no storage

    consumer = JetstreamConsumer(
        connector,
        load_checkpoint=load_checkpoint,
        save_checkpoint=save_checkpoint,
        handle_event=handle_event,
        stop_event=stop_event,
    )

    try:
        logger.info(
            "jetstream_runner_starting",
            extra={"endpoints": config.ordered_endpoints(), "source_key": config.source_key},
        )
        await consumer.run_forever()
    finally:
        await connector.close()
        logger.info(
            "jetstream_runner_stopped",
            extra={"processed": consumer.processed, "errors": consumer.errors},
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Bluesky Jetstream consumer")
    parser.add_argument(
        "--region",
        choices=sorted(REGIONAL_ENDPOINTS.keys()),
        default=None,
        help="Prefer a regional endpoint",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        default=None,
        help="Override endpoint URL (repeatable). Default: built-in regional list.",
    )
    parser.add_argument(
        "--source-key",
        default="bluesky:jetstream",
        help="Checkpoint source_key",
    )
    args = parser.parse_args(argv)

    config_kwargs: dict[str, Any] = {"source_key": args.source_key}
    if args.region:
        config_kwargs["region"] = args.region
    if args.endpoint:
        config_kwargs["endpoints"] = args.endpoint
    config = BlueskyJetstreamConfig.model_validate(config_kwargs)
    raise SystemExit(asyncio.run(_run(config)))


if __name__ == "__main__":
    main(sys.argv[1:])
