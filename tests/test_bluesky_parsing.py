"""Jetstream frame parsing tests (fixture-based)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pulse.connectors.bluesky.parsing import (
    StreamDeleteEvent,
    StreamPostEvent,
    StreamSkipEvent,
    parse_frame,
)
from pulse.connectors.types import ConnectorError

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_parse_legacy_create_post() -> None:
    event = parse_frame(
        _load("jetstream_commit_create.json"),
        collected_at=datetime(2024, 9, 9, 20, 0, tzinfo=UTC),
        source_version="1.0.0",
    )
    assert isinstance(event, StreamPostEvent)
    assert event.mention.source == "bluesky"
    assert event.mention.external_id.endswith("/app.bsky.feed.post/3l3qo2vuowo2b")
    assert event.mention.content == "hello from the public firehose"
    assert event.mention.author_id == "did:plc:exampleposter000000000001"
    assert event.mention.canonical_url is not None
    assert event.cursor.time_us == 1725911162329308
    assert event.cursor.seq == 12345


def test_parse_legacy_delete() -> None:
    event = parse_frame(
        _load("jetstream_commit_delete.json"),
        collected_at=datetime.now(UTC),
        source_version="1.0.0",
    )
    assert isinstance(event, StreamDeleteEvent)
    assert event.external_id == (
        "at://did:plc:exampleposter000000000001/app.bsky.feed.post/3l3qo2vuowo2b"
    )
    assert event.cursor.time_us == 1725911162999999


def test_parse_v2_message_envelope() -> None:
    event = parse_frame(
        _load("jetstream_v2_message.json"),
        collected_at=datetime.now(UTC),
        source_version="1.0.0",
    )
    assert isinstance(event, StreamPostEvent)
    assert event.mention.content == "v2 framed post"
    assert event.cursor.seq == 99901
    assert event.cursor.time_us is not None


def test_parse_skips_non_post_collection() -> None:
    payload = _load("jetstream_commit_create.json")
    payload["commit"]["collection"] = "app.bsky.feed.like"
    event = parse_frame(payload, collected_at=datetime.now(UTC), source_version="1")
    assert isinstance(event, StreamSkipEvent)
    assert "collection" in event.reason


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ConnectorError):
        parse_frame("{not-json", collected_at=datetime.now(UTC), source_version="1")


def test_create_without_record_raises() -> None:
    payload = _load("jetstream_commit_create.json")
    del payload["commit"]["record"]
    with pytest.raises(ConnectorError):
        parse_frame(payload, collected_at=datetime.now(UTC), source_version="1")
