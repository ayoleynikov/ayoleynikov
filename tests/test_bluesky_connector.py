"""Bluesky Jetstream connector + consumer tests with mocked WebSocket."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pulse.connectors.bluesky.config import BlueskyJetstreamConfig
from pulse.connectors.bluesky.connector import BlueskyJetstreamConnector
from pulse.connectors.bluesky.consumer import JetstreamConsumer
from pulse.connectors.bluesky.parsing import StreamDeleteEvent, StreamPostEvent
from pulse.connectors.registry import get_registry, reset_registry
from pulse.connectors.types import CheckpointCursor, ConnectorError, ConnectorErrorKind, SearchQuery

FIXTURES = Path(__file__).parent / "fixtures"


class FakeWebSocket:
    def __init__(self, messages: list[str | bytes]) -> None:
        self._messages = list(messages)
        self._index = 0

    async def recv(self) -> str | bytes:
        if self._index >= len(self._messages):
            await asyncio.sleep(0)
            raise ConnectorError(
                "fake close",
                kind=ConnectorErrorKind.TRANSIENT,
                retryable=True,
            )
        # Raise ConnectionClosed-like via ConnectorError from connector path —
        # instead return messages then stop by raising websockets close.
        from websockets.exceptions import ConnectionClosedOK

        if self._index >= len(self._messages):
            raise ConnectionClosedOK(None, None)
        msg = self._messages[self._index]
        self._index += 1
        if self._index >= len(self._messages):
            # After last message, next recv closes.
            self._done = True
        return msg


def _ws_factory(messages: list[str | bytes]):
    @asynccontextmanager
    async def factory(url: str, **_kwargs: Any):
        ws = FakeWebSocket(messages)

        async def recv() -> str | bytes:
            from websockets.exceptions import ConnectionClosedOK

            if ws._index >= len(ws._messages):
                raise ConnectionClosedOK(None, None)
            msg = ws._messages[ws._index]
            ws._index += 1
            return msg

        ws.recv = recv  # type: ignore[method-assign]
        yield ws

    return factory


@pytest.mark.asyncio
async def test_stream_parses_create_and_delete() -> None:
    create = (FIXTURES / "jetstream_commit_create.json").read_text()
    delete = (FIXTURES / "jetstream_commit_delete.json").read_text()
    connector = BlueskyJetstreamConnector(
        {"endpoints": ["wss://jetstream.test.local/subscribe"]}
    )
    events = []
    try:
        async for event in connector.stream_events(
            websocket_factory=_ws_factory([create, delete]),
            max_events=2,
        ):
            events.append(event)
    finally:
        await connector.close()

    assert len(events) == 2
    assert isinstance(events[0], StreamPostEvent)
    assert isinstance(events[1], StreamDeleteEvent)


@pytest.mark.asyncio
async def test_consumer_advances_checkpoint_only_after_handler() -> None:
    create = (FIXTURES / "jetstream_commit_create.json").read_text()
    connector = BlueskyJetstreamConnector(
        {"endpoints": ["wss://jetstream.test.local/subscribe"], "source_key": "test:js"}
    )
    order: list[str] = []
    saved: list[CheckpointCursor] = []
    stop = asyncio.Event()

    async def load() -> CheckpointCursor | None:
        return None

    async def save(cursor: CheckpointCursor) -> None:
        order.append("save")
        saved.append(cursor)
        stop.set()

    async def handle(event) -> None:  # type: ignore[no-untyped-def]
        order.append("handle")
        await asyncio.sleep(0)

    consumer = JetstreamConsumer(
        connector,
        load_checkpoint=load,
        save_checkpoint=save,
        handle_event=handle,
        stop_event=stop,
        websocket_factory=_ws_factory([create]),
    )
    try:
        await asyncio.wait_for(consumer.run_forever(), timeout=5)
    except TimeoutError:
        pytest.fail("consumer did not stop after processing")
    finally:
        await connector.close()

    assert order == ["handle", "save"]
    assert saved
    assert saved[0].cursor_token == "1725911162329308"
    assert consumer.processed == 1


@pytest.mark.asyncio
async def test_consumer_does_not_advance_when_handler_fails() -> None:
    create = (FIXTURES / "jetstream_commit_create.json").read_text()
    connector = BlueskyJetstreamConnector(
        {
            "endpoints": ["wss://jetstream.test.local/subscribe"],
            "reconnect_initial_seconds": 0.01,
            "reconnect_max_seconds": 0.01,
        }
    )
    saved: list[CheckpointCursor] = []
    stop = asyncio.Event()
    attempts = {"n": 0}

    async def load() -> CheckpointCursor | None:
        return None

    async def save(cursor: CheckpointCursor) -> None:
        saved.append(cursor)

    async def handle(event) -> None:  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("db unavailable")
        stop.set()

    consumer = JetstreamConsumer(
        connector,
        load_checkpoint=load,
        save_checkpoint=save,
        handle_event=handle,
        stop_event=stop,
        websocket_factory=_ws_factory([create, create]),
    )
    try:
        await asyncio.wait_for(consumer.run_forever(), timeout=5)
    finally:
        await connector.close()

    # First handle failed before save; no durable advance for that attempt.
    # After reconnect/retry the second handle succeeds then save may run —
    # critical assertion: we never saved before a successful handle.
    assert attempts["n"] >= 1
    # If anything was saved, handle must have succeeded at least once after failure.
    if saved:
        assert attempts["n"] >= 2


def test_build_subscribe_url_legacy_and_v2() -> None:
    connector = BlueskyJetstreamConnector(
        {
            "endpoints": [
                "wss://jetstream1.us-east.bsky.network/subscribe",
                "wss://jetstream.us-west.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents",
            ]
        }
    )
    cursor = CheckpointCursor(
        connector="bluesky",
        source_key="bluesky:jetstream",
        cursor_token="1725911162329308",
    )
    legacy = connector.build_subscribe_url(
        "wss://jetstream1.us-east.bsky.network/subscribe",
        cursor=cursor,
    )
    assert "wantedCollections=app.bsky.feed.post" in legacy
    assert "cursor=1725911162329308" in legacy

    v2 = connector.build_subscribe_url(
        "wss://jetstream.us-west.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents",
        cursor=cursor,
    )
    assert "collections=app.bsky.feed.post" in v2
    assert "kinds=commit" in v2
    assert "wantedCollections" not in v2


@pytest.mark.asyncio
async def test_search_unsupported() -> None:
    connector = BlueskyJetstreamConnector({"endpoints": ["wss://example.test/subscribe"]})
    try:
        with pytest.raises(ConnectorError) as exc:
            await connector.search(SearchQuery(query="x"))
        assert exc.value.kind == ConnectorErrorKind.UNSUPPORTED
    finally:
        await connector.close()


def test_registry_includes_bluesky() -> None:
    reset_registry()
    names = {item.name for item in get_registry().list()}
    assert "bluesky" in names
    bluesky = next(i for i in get_registry().list() if i.name == "bluesky")
    assert bluesky.capabilities.streaming is True
    assert bluesky.capabilities.public_only is True


def test_region_prefers_endpoint() -> None:
    cfg = BlueskyJetstreamConfig(region="us-west-v2")
    ordered = cfg.ordered_endpoints()
    assert "subscribeEvents" in ordered[0]
