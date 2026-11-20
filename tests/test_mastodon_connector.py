"""Mastodon connector tests — mocked HTTP, instance-local only."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pulse.connectors.mastodon.connector import MastodonConnector
from pulse.connectors.mastodon.parsing import parse_statuses
from pulse.connectors.registry import get_registry, reset_registry
from pulse.connectors.types import ConnectorError, ConnectorErrorKind, SearchQuery
from pulse.usage.recorder import reset_usage_recorder
from datetime import UTC, datetime

FIXTURES = Path(__file__).parent / "fixtures"


def _statuses() -> list:
    return json.loads((FIXTURES / "mastodon_statuses.json").read_text())


def _instance() -> dict:
    return json.loads((FIXTURES / "mastodon_instance.json").read_text())


def _search() -> dict:
    return json.loads((FIXTURES / "mastodon_search.json").read_text())


@pytest.fixture(autouse=True)
def _reset_usage() -> None:
    reset_usage_recorder()


@pytest.mark.asyncio
async def test_hashtag_search_instance_local() -> None:
    statuses = _statuses()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/v1/timelines/tag/pulse")
        assert "mastodon.example" in str(request.url)
        return httpx.Response(200, json=statuses)

    connector = MastodonConnector(
        {"instance_url": "https://mastodon.example", "hashtag": "pulse"}
    )
    connector._client = httpx.AsyncClient(
        base_url="https://mastodon.example",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await connector.search(SearchQuery(query="#pulse", limit=10))
        assert len(result.mentions) == 2
        assert result.mentions[0].source == "mastodon"
        assert result.mentions[0].metadata["search_scope"] == "instance_local"
        assert result.mentions[0].content == "Hello from #pulse"
        assert result.next_cursor is not None
        assert result.next_cursor.extra["federation_wide_search"] is False
        assert result.accounting.http_requests == 1
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_v2_search_requires_token() -> None:
    connector = MastodonConnector({"instance_url": "https://mastodon.example"})
    connector._client = httpx.AsyncClient(
        base_url="https://mastodon.example",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    try:
        with pytest.raises(ConnectorError) as exc:
            await connector.search(SearchQuery(query="brand listening platform", limit=5))
        assert exc.value.kind == ConnectorErrorKind.AUTH
        assert "federation-wide" in str(exc.value).lower() or "instance-local" in str(exc.value).lower()
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_v2_search_with_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/v2/search")
        assert request.url.params.get("resolve") == "false"
        return httpx.Response(200, json=_search())

    connector = MastodonConnector(
        {
            "instance_url": "https://mastodon.example",
            "access_token": "test-token-not-real",
        }
    )
    connector._client = httpx.AsyncClient(
        base_url="https://mastodon.example",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test-token-not-real"},
    )
    try:
        result = await connector.search(SearchQuery(query="brand listening", limit=5))
        assert len(result.mentions) == 1
        assert result.mentions[0].external_id.startswith("mastodon.example:")
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_fetch_public_timeline_and_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/v1/instance"):
            return httpx.Response(200, json=_instance())
        assert request.url.path.endswith("/api/v1/timelines/public")
        return httpx.Response(200, json=_statuses())

    connector = MastodonConnector({"instance_url": "https://mastodon.example"})
    connector._client = httpx.AsyncClient(
        base_url="https://mastodon.example",
        transport=httpx.MockTransport(handler),
    )
    try:
        health = await connector.healthcheck()
        assert health.healthy is True
        assert health.details["federation_wide_search"] is False

        fetched = await connector.fetch_updates()
        assert len(fetched.mentions) == 2
        assert fetched.next_cursor.extra["since_id"] == "110001"
    finally:
        await connector.close()


def test_parse_rejects_non_list() -> None:
    with pytest.raises(ConnectorError):
        parse_statuses(
            {"statuses": []},
            collected_at=datetime.now(UTC),
            source_version="1",
            instance_host="x",
        )


def test_registry_includes_mastodon_not_federation_wide() -> None:
    reset_registry()
    reg = next(i for i in get_registry().list() if i.name == "mastodon")
    assert reg.capabilities.search is True
    assert reg.capabilities.streaming is True
    assert reg.policies["federation_wide_search"] is False
    assert reg.policies["search_scope"] == "instance_local"
