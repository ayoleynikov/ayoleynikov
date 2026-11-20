"""GDELT connector tests with mocked HTTP — no fabricated success on errors."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pulse.connectors.gdelt.connector import GDELTConnector
from pulse.connectors.gdelt.parsing import parse_artlist_response
from pulse.connectors.registry import get_registry, reset_registry
from pulse.connectors.types import ConnectorError, ConnectorErrorKind, SearchQuery
from datetime import UTC, datetime

FIXTURES = Path(__file__).parent / "fixtures"


def _artlist() -> dict:
    return json.loads((FIXTURES / "gdelt_artlist.json").read_text())


@pytest.mark.asyncio
async def test_search_parses_articles() -> None:
    payload = _artlist()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "query" in request.url.params
        return httpx.Response(200, json=payload)

    connector = GDELTConnector({"query": "Acme", "max_records": 50, "timespan": "24h"})
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await connector.search(SearchQuery(query="Acme", limit=10))
        assert len(result.mentions) == 2
        assert result.mentions[0].source == "gdelt"
        assert result.mentions[0].content is None  # ArtList has no body — not invented
        assert result.accounting.http_requests == 1
        assert result.accounting.items_fetched == 2
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_empty_body_is_error_not_success() -> None:
    connector = GDELTConnector({"query": "x", "max_retries": 1})
    connector._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b""))
    )
    try:
        with pytest.raises(ConnectorError) as exc:
            await connector.fetch_updates()
        assert exc.value.kind == ConnectorErrorKind.TRANSIENT
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_html_response_classified_as_rate_limit() -> None:
    connector = GDELTConnector({"query": "x", "max_retries": 1})
    connector._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=b"<html>overloaded</html>")
        )
    )
    try:
        with pytest.raises(ConnectorError) as exc:
            await connector.search(SearchQuery(limit=5))
        assert exc.value.kind == ConnectorErrorKind.RATE_LIMIT
    finally:
        await connector.close()


def test_parse_requires_articles_key() -> None:
    with pytest.raises(ConnectorError):
        parse_artlist_response(
            {"not_articles": []},
            collected_at=datetime.now(UTC),
            source_version="1",
        )


def test_registry_includes_gdelt() -> None:
    reset_registry()
    names = {i.name for i in get_registry().list()}
    assert "gdelt" in names
    gdelt = next(i for i in get_registry().list() if i.name == "gdelt")
    assert gdelt.capabilities.historical is True
