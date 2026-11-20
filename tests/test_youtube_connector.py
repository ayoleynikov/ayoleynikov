"""YouTube Data API connector tests — mocked fixtures, quota enforced."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pulse.connectors.registry import DISABLED_CONNECTORS, get_registry, reset_registry
from pulse.connectors.types import ConnectorError, ConnectorErrorKind, SearchQuery
from pulse.connectors.youtube.connector import YouTubeConnector
from pulse.connectors.youtube.quota import QuotaLedger
from pulse.usage.recorder import reset_usage_recorder

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def _reset_usage() -> None:
    reset_usage_recorder()


def _connector(**overrides: object) -> YouTubeConnector:
    cfg = {
        "api_key": "test-youtube-key-not-real",
        "daily_quota_units": 300,
        "quota_warning_threshold": 0.5,
        "default_query": "pulse",
        **overrides,
    }
    return YouTubeConnector(cfg)


@pytest.mark.asyncio
async def test_search_parses_and_paginates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "key" in request.url.params
        assert request.url.params["key"] == "test-youtube-key-not-real"
        assert request.url.path.endswith("/search")
        return httpx.Response(200, json=_load("youtube_search.json"))

    connector = _connector()
    connector._client = httpx.AsyncClient(
        base_url="https://www.googleapis.com/youtube/v3",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await connector.search(SearchQuery(query="pulse", limit=10))
        assert len(result.mentions) == 2
        assert result.mentions[0].external_id == "video:vid001"
        assert result.mentions[0].title == "Pulse demo"
        assert result.next_cursor is not None
        assert result.next_cursor.cursor_token == "CAUQAA"
        assert result.next_cursor.extra["unlimited_access"] is False
        assert connector.quota.units_used == 100  # search.list cost
        assert result.exhausted is False
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_video_metadata_and_comments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/videos"):
            return httpx.Response(200, json=_load("youtube_videos.json"))
        if path.endswith("/commentThreads"):
            return httpx.Response(200, json=_load("youtube_comments.json"))
        return httpx.Response(404, json={"error": {"message": "unexpected", "code": 404}})

    connector = _connector()
    connector._client = httpx.AsyncClient(
        base_url="https://www.googleapis.com/youtube/v3",
        transport=httpx.MockTransport(handler),
    )
    try:
        videos = await connector.fetch_video_metadata(["vid001"])
        assert len(videos) == 1
        assert videos[0].engagement["views"] == 1000

        comments, next_token = await connector.fetch_comments("vid001", max_results=10)
        assert next_token is None
        assert len(comments) == 1
        assert comments[0].external_id == "comment:comment001"
        assert connector.quota.units_used == 2  # videos.list + commentThreads.list
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_comments_disabled_is_permanent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": 403,
                    "message": "comments disabled",
                    "errors": [{"reason": "commentsDisabled"}],
                }
            },
        )

    connector = _connector()
    connector._client = httpx.AsyncClient(
        base_url="https://www.googleapis.com/youtube/v3",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ConnectorError) as exc:
            await connector.fetch_comments("vid001")
        assert exc.value.kind == ConnectorErrorKind.PERMANENT
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_quota_exhausted_blocks_search() -> None:
    connector = _connector(daily_quota_units=50)  # search costs 100
    connector._client = httpx.AsyncClient(
        base_url="https://www.googleapis.com/youtube/v3",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_load("youtube_search.json"))),
    )
    try:
        with pytest.raises(ConnectorError) as exc:
            await connector.search(SearchQuery(query="x", limit=5))
        assert exc.value.kind == ConnectorErrorKind.RATE_LIMIT
        assert "unlimited" in str(exc.value).lower()
    finally:
        await connector.close()


def test_quota_ledger_charges_and_resets_day() -> None:
    ledger = QuotaLedger(daily_budget=150)
    assert ledger.charge("search.list") == 100
    assert ledger.remaining() == 50
    with pytest.raises(ConnectorError):
        ledger.charge("search.list")
    assert ledger.charge("videos.list") == 1


def test_registry_youtube_and_reddit_disabled() -> None:
    reset_registry()
    names = {i.name for i in get_registry().list()}
    assert "youtube" in names
    assert "mastodon" in names
    assert "reddit" not in names
    assert "reddit" in DISABLED_CONNECTORS

    yt = next(i for i in get_registry().list() if i.name == "youtube")
    assert yt.policies["unlimited_access"] is False
    assert yt.policies["quota_accounting"] is True

    manifest = get_registry().health_manifest()
    reddit = next(i for i in manifest if i["name"] == "reddit")
    assert reddit["enabled"] is False

    with pytest.raises(ConnectorError) as exc:
        get_registry().get("reddit")
    assert exc.value.kind == ConnectorErrorKind.UNSUPPORTED
