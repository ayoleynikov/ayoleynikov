"""Long-running Jetstream consumer with reconnect backoff and durable checkpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pulse.connectors.bluesky.connector import BlueskyJetstreamConnector
from pulse.connectors.bluesky.parsing import (
    JetstreamCursor,
    StreamDeleteEvent,
    StreamEvent,
    StreamPostEvent,
    StreamSkipEvent,
)
from pulse.connectors.types import CheckpointCursor, ConnectorError
from pulse.logging import get_logger

logger = get_logger(__name__)

DurableHandler = Callable[[StreamEvent], Awaitable[None]]
CheckpointSaver = Callable[[CheckpointCursor], Awaitable[None]]
CheckpointLoader = Callable[[], Awaitable[CheckpointCursor | None]]


class JetstreamConsumer:
    """Reconnecting consumer: process durably, then advance the checkpoint."""

    def __init__(
        self,
        connector: BlueskyJetstreamConnector,
        *,
        load_checkpoint: CheckpointLoader,
        save_checkpoint: CheckpointSaver,
        handle_event: DurableHandler,
        stop_event: asyncio.Event | None = None,
        websocket_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.connector = connector
        self.load_checkpoint = load_checkpoint
        self.save_checkpoint = save_checkpoint
        self.handle_event = handle_event
        self.stop_event = stop_event or asyncio.Event()
        self.websocket_factory = websocket_factory
        self._processed = 0
        self._errors = 0

    @property
    def processed(self) -> int:
        return self._processed

    @property
    def errors(self) -> int:
        return self._errors

    async def run_forever(self) -> None:
        """Run until ``stop_event`` is set."""
        assert isinstance(self.connector.config, object)
        cfg = self.connector.config
        delay = cfg.reconnect_initial_seconds
        while not self.stop_event.is_set():
            try:
                cursor = await self.load_checkpoint()
                async for event in self.connector.stream_events(
                    cursor=cursor,
                    websocket_factory=self.websocket_factory,
                ):
                    if self.stop_event.is_set():
                        return
                    await self._process_durably(event)
                # Clean close — reconnect with backoff.
                delay = cfg.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except ConnectorError as exc:
                self._errors += 1
                logger.error(
                    "jetstream_consumer_error",
                    extra={"error": str(exc), "kind": exc.kind.value, "retryable": exc.retryable},
                )
                if not exc.retryable:
                    raise
            except Exception as exc:  # noqa: BLE001
                self._errors += 1
                logger.exception("jetstream_consumer_unexpected", extra={"error": str(exc)})

            if self.stop_event.is_set():
                return
            logger.info("jetstream_reconnect_backoff", extra={"seconds": delay})
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
                return
            except TimeoutError:
                pass
            delay = min(delay * cfg.reconnect_multiplier, cfg.reconnect_max_seconds)

    async def _process_durably(self, event: StreamEvent) -> None:
        """Handle the event first; only then advance the cursor checkpoint."""
        await self.handle_event(event)

        cursor_pos: JetstreamCursor | None = None
        if isinstance(event, (StreamPostEvent, StreamDeleteEvent)):
            cursor_pos = event.cursor
        elif isinstance(event, StreamSkipEvent):
            cursor_pos = event.cursor

        if cursor_pos is None:
            return

        # Durable processing completed — safe to advance.
        checkpoint = CheckpointCursor(
            connector=self.connector.name,
            source_key=self.connector.source_key(),
            cursor_token=cursor_pos.as_token(),
            extra={
                "time_us": cursor_pos.time_us,
                "seq": cursor_pos.seq,
                "advanced_at": datetime.now(UTC).isoformat(),
            },
        )
        await self.save_checkpoint(checkpoint)
        self._processed += 1
