"""Bluesky Jetstream connector — streaming public firehose consumer."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Awaitable
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import websockets
from websockets.asyncio.client import connect as ws_connect

from pulse.connectors.base import BaseConnector
from pulse.connectors.bluesky.config import BlueskyJetstreamConfig
from pulse.connectors.bluesky.parsing import (
    StreamDeleteEvent,
    StreamEvent,
    StreamInfoEvent,
    StreamPostEvent,
    StreamSkipEvent,
    parse_frame,
)
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorErrorKind,
    FetchResult,
    HealthStatus,
    SearchQuery,
    SearchResult,
)
from pulse.logging import get_logger

logger = get_logger(__name__)

EventHandler = Callable[[StreamEvent], Awaitable[None]]


class BlueskyJetstreamConnector(BaseConnector):
    """Consume public Bluesky Jetstream events (v2 XRPC or legacy /subscribe)."""

    name: ClassVar[str] = "bluesky"
    version: ClassVar[str] = "1.0.0"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        search=False,
        incremental_fetch=True,
        streaming=True,
        historical=False,
        supports_etag=False,
        supports_last_modified=False,
        public_only=True,
        max_page_size=None,
    )
    config_schema: ClassVar[type[BlueskyJetstreamConfig]] = BlueskyJetstreamConfig

    def __init__(self, config: BlueskyJetstreamConfig | dict[str, Any]) -> None:
        super().__init__(config)
        assert isinstance(self.config, BlueskyJetstreamConfig)
        self._closed = False
        self._http = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": self.config.user_agent},
            follow_redirects=True,
        )

    def source_key(self) -> str:
        assert isinstance(self.config, BlueskyJetstreamConfig)
        return self.config.source_key

    async def search(
        self,
        query: SearchQuery,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> SearchResult:
        raise ConnectorError(
            "bluesky jetstream does not support search; use the firehose stream",
            kind=ConnectorErrorKind.UNSUPPORTED,
            retryable=False,
        )

    async def fetch_updates(
        self,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> FetchResult:
        """Collect a short batch from the live stream (SDK contract / tests).

        Prefer ``stream_events`` / the long-running runner for production.
        """
        assert isinstance(self.config, BlueskyJetstreamConfig)
        self.accounting.reset()
        mentions = []
        next_cursor = cursor
        limit = 25
        async for event in self.stream_events(cursor=cursor, max_events=limit, max_seconds=15.0):
            if isinstance(event, StreamPostEvent):
                mentions.append(event.mention)
                self.accounting.record_items(1)
                next_cursor = _checkpoint_from_event_cursor(self.source_key(), event.cursor)
            elif isinstance(event, StreamDeleteEvent):
                next_cursor = _checkpoint_from_event_cursor(self.source_key(), event.cursor)
            elif isinstance(event, StreamSkipEvent) and event.cursor is not None:
                next_cursor = _checkpoint_from_event_cursor(self.source_key(), event.cursor)
        return FetchResult(
            mentions=mentions,
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            not_modified=False,
        )

    async def healthcheck(self) -> HealthStatus:
        assert isinstance(self.config, BlueskyJetstreamConfig)
        endpoint = self.config.ordered_endpoints()[0]
        # Convert wss→https for a cheap reachability probe of the host.
        probe = endpoint.replace("wss://", "https://").replace("ws://", "http://")
        probe = probe.split("?", 1)[0]
        try:
            response = await self._http.get(probe)
            self.accounting.record_http(bytes_downloaded=len(response.content or b""))
            # WebSocket upgrade endpoints often return 400/404/426 on plain GET — host up is enough.
            healthy = response.status_code < 500
            return HealthStatus(
                healthy=healthy,
                connector=self.name,
                message="ok" if healthy else f"HTTP {response.status_code}",
                details={"endpoint": endpoint, "status_code": response.status_code},
            )
        except httpx.HTTPError as exc:
            return HealthStatus(
                healthy=False,
                connector=self.name,
                message=str(exc),
                details={"endpoint": endpoint},
            )

    async def close(self) -> None:
        self._closed = True
        await self._http.aclose()

    def build_subscribe_url(
        self,
        endpoint: str,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> str:
        """Build the WebSocket URL with collection/kind/cursor query params."""
        assert isinstance(self.config, BlueskyJetstreamConfig)
        parts = urlsplit(endpoint)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        v2 = self.config.is_v2_endpoint(endpoint)

        if v2:
            # v2 rejects legacy wanted* params.
            for key in list(query):
                if key.startswith("wanted"):
                    del query[key]
            # Repeated params built manually below.
            pairs: list[tuple[str, str]] = [
                (k, v) for k, v in query.items() if k not in {"collections", "kinds", "cursor"}
            ]
            for collection in self.config.collections:
                pairs.append(("collections", collection))
            for kind in self.config.kinds:
                pairs.append(("kinds", kind))
            cursor_value = _resume_cursor_value(cursor, rewind_us=self.config.cursor_rewind_us)
            if cursor_value is not None:
                pairs.append(("cursor", cursor_value))
            new_query = urlencode(pairs)
        else:
            pairs = [(k, v) for k, v in query.items() if k not in {"wantedCollections", "cursor"}]
            for collection in self.config.collections:
                pairs.append(("wantedCollections", collection))
            cursor_value = _resume_cursor_value(cursor, rewind_us=self.config.cursor_rewind_us)
            if cursor_value is not None:
                pairs.append(("cursor", cursor_value))
            new_query = urlencode(pairs)

        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, ""))

    async def stream_events(
        self,
        *,
        cursor: CheckpointCursor | None = None,
        max_events: int | None = None,
        max_seconds: float | None = None,
        websocket_factory: Callable[..., Any] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield parsed events from the first reachable endpoint (single connection).

        Reconnect/backoff lives in ``run_with_reconnect`` so durable handlers own the loop.
        """
        assert isinstance(self.config, BlueskyJetstreamConfig)
        if self._closed:
            raise ConnectorError(
                "connector is closed",
                kind=ConnectorErrorKind.PERMANENT,
                retryable=False,
            )

        connect = websocket_factory or ws_connect
        last_error: Exception | None = None
        for endpoint in self.config.ordered_endpoints():
            url = self.build_subscribe_url(endpoint, cursor=cursor)
            try:
                async for event in self._consume_connection(
                    url,
                    connect=connect,
                    max_events=max_events,
                    max_seconds=max_seconds,
                ):
                    yield event
                return
            except ConnectorError:
                raise
            except Exception as exc:  # noqa: BLE001 — try next regional endpoint
                last_error = exc
                logger.warning(
                    "jetstream_endpoint_failed",
                    extra={"endpoint": endpoint, "error": str(exc)},
                )
                continue

        raise ConnectorError(
            f"all jetstream endpoints failed: {last_error}",
            kind=ConnectorErrorKind.TRANSIENT,
            retryable=True,
        )

    async def _consume_connection(
        self,
        url: str,
        *,
        connect: Callable[..., Any],
        max_events: int | None,
        max_seconds: float | None,
    ) -> AsyncIterator[StreamEvent]:
        assert isinstance(self.config, BlueskyJetstreamConfig)
        count = 0
        started = datetime.now(UTC)
        extra_headers = {"User-Agent": self.config.user_agent}
        async with connect(
            url,
            additional_headers=extra_headers,
            max_size=self.config.max_message_bytes,
            open_timeout=30,
        ) as websocket:
            self.accounting.record_http(bytes_downloaded=0)
            while True:
                if max_events is not None and count >= max_events:
                    return
                if max_seconds is not None:
                    elapsed = (datetime.now(UTC) - started).total_seconds()
                    if elapsed >= max_seconds:
                        return
                try:
                    message = await websocket.recv()
                except websockets.exceptions.ConnectionClosed as exc:
                    raise ConnectorError(
                        f"jetstream connection closed: {exc}",
                        kind=ConnectorErrorKind.TRANSIENT,
                        retryable=True,
                    ) from exc

                if isinstance(message, bytes):
                    self.accounting.record_http(bytes_downloaded=len(message))
                elif isinstance(message, str):
                    self.accounting.record_http(bytes_downloaded=len(message.encode("utf-8")))

                event = parse_frame(
                    message,
                    collected_at=datetime.now(UTC),
                    source_version=self.version,
                    wanted_collections=self.config.collections,
                )
                if event is None:
                    continue
                if isinstance(event, StreamInfoEvent):
                    logger.info(
                        "jetstream_info",
                        extra={"name": event.name, "message": event.message},
                    )
                count += 1
                yield event


def _resume_cursor_value(cursor: CheckpointCursor | None, *, rewind_us: int) -> str | None:
    if cursor is None:
        return None
    token = cursor.cursor_token
    if not token:
        # Fall back to time_us stored in extra.
        time_us = cursor.extra.get("time_us")
        if time_us is not None:
            token = str(time_us)
        else:
            return None
    try:
        value = int(token)
    except ValueError:
        return token
    if rewind_us and value >= 1_000_000_000_000_000:  # timestamp-style (>= 1e15)
        value = max(0, value - rewind_us)
    return str(value)


def _checkpoint_from_event_cursor(source_key: str, cursor: Any) -> CheckpointCursor:
    from pulse.connectors.bluesky.parsing import JetstreamCursor

    assert isinstance(cursor, JetstreamCursor)
    return CheckpointCursor(
        connector="bluesky",
        source_key=source_key,
        cursor_token=cursor.as_token(),
        extra={
            "time_us": cursor.time_us,
            "seq": cursor.seq,
        },
    )
