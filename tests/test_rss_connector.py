"""RSS/Atom connector tests using fixtures — no silent empty success."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pulse.connectors.rss.connector import RSSConnector
from pulse.connectors.rss.parsing import parse_feed
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorError,
    ConnectorErrorKind,
    SearchQuery,
)
from datetime import UTC, datetime

FIXTURES = Path(__file__).parent / "fixtures"


def _rss_body() -> bytes:
    return (FIXTURES / "sample.rss.xml").read_bytes()


def _atom_body() -> bytes:
    return (FIXTURES / "sample.atom.xml").read_bytes()


def _invalid_body() -> bytes:
    return (FIXTURES / "invalid.feed.xml").read_bytes()


@pytest.mark.asyncio
async def test_fetch_parses_rss_entries() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=_rss_body(),
            headers={"ETag": '"v1"', "Last-Modified": "Mon, 01 Jan 2024 12:00:00 GMT"},
        )
    )
    connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
    connector._client = httpx.AsyncClient(transport=transport)
    try:
        result = await connector.fetch_updates()
        assert result.not_modified is False
        assert len(result.mentions) == 2
        assert result.accounting.http_requests == 1
        assert result.accounting.items_fetched == 2
        assert result.next_cursor is not None
        assert result.next_cursor.etag == '"v1"'
        assert result.next_cursor.last_modified == "Mon, 01 Jan 2024 12:00:00 GMT"
        first = result.mentions[0]
        assert first.source == "rss"
        assert first.title == "First Article"
        assert first.canonical_url == "https://example.com/blog/first-article"
        assert first.mention_id
        assert first.content_hash
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_fetch_atom_entries() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=_atom_body()))
    connector = RSSConnector({"feed_url": "https://example.com/atom.xml"})
    connector._client = httpx.AsyncClient(transport=transport)
    try:
        result = await connector.fetch_updates()
        assert len(result.mentions) == 1
        assert result.mentions[0].external_id == "urn:example:atom-one"
        assert result.mentions[0].author_name == "Bob"
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_etag_not_modified_returns_empty_with_flag() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("if-none-match") == '"v1"'
        return httpx.Response(304, headers={"ETag": '"v1"'})

    connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cursor = CheckpointCursor(
        connector="rss",
        source_key="https://example.com/feed.xml",
        etag='"v1"',
        last_modified="Mon, 01 Jan 2024 12:00:00 GMT",
        seen_external_ids=["https://example.com/blog/first-article/"],
    )
    try:
        result = await connector.fetch_updates(cursor=cursor)
        assert result.not_modified is True
        assert result.mentions == []
        assert result.accounting.not_modified is True
        assert result.next_cursor is not None
        assert result.next_cursor.etag == '"v1"'
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_incremental_skips_seen_ids() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=_rss_body()))
    connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
    connector._client = httpx.AsyncClient(transport=transport)
    cursor = CheckpointCursor(
        connector="rss",
        source_key="https://example.com/feed.xml",
        seen_external_ids=["https://example.com/blog/first-article/"],
    )
    try:
        result = await connector.fetch_updates(cursor=cursor)
        assert len(result.mentions) == 1
        assert result.mentions[0].external_id == "urn:example:second"
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_http_error_is_classified_not_silent() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="down"))
    connector = RSSConnector({"feed_url": "https://example.com/feed.xml", "max_retries": 1})
    connector._client = httpx.AsyncClient(transport=transport)
    try:
        with pytest.raises(ConnectorError) as exc_info:
            await connector.fetch_updates()
        assert exc_info.value.kind == ConnectorErrorKind.TRANSIENT
        assert exc_info.value.retryable is True
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_invalid_feed_raises_parse_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=_invalid_body()))
    connector = RSSConnector({"feed_url": "https://example.com/not-a-feed.xml"})
    connector._client = httpx.AsyncClient(transport=transport)
    try:
        with pytest.raises(ConnectorError) as exc_info:
            await connector.fetch_updates()
        assert exc_info.value.kind == ConnectorErrorKind.PARSE
    finally:
        await connector.close()


def test_parse_feed_rejects_garbage() -> None:
    with pytest.raises(ConnectorError) as exc_info:
        parse_feed(
            b"<html>nope</html>",
            feed_url="https://example.com/x",
            collected_at=datetime.now(UTC),
            source_version="1",
            max_entries=10,
        )
    assert exc_info.value.kind == ConnectorErrorKind.PARSE


@pytest.mark.asyncio
async def test_search_filters_keyword() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=_rss_body()))
    connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
    connector._client = httpx.AsyncClient(transport=transport)
    try:
        result = await connector.search(SearchQuery(query="Second"))
        assert len(result.mentions) == 1
        assert result.mentions[0].title == "Second Article"
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_validate_config_requires_feed_url() -> None:
    with pytest.raises(Exception):
        RSSConnector({})
