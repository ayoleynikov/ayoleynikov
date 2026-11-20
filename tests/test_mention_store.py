"""Poll/store path tests — failures must surface; no silent empty success."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pulse.connectors.rss.connector import RSSConnector
from pulse.connectors.types import ConnectorError, ConnectorErrorKind
from pulse.ingestion.store import MentionStore, poll_rss_feed

FIXTURES = Path(__file__).parent / "fixtures"


class FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_poll_rss_feed_surfaces_connector_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom_fetch(self, *, cursor=None):  # type: ignore[no-untyped-def]
        raise ConnectorError("upstream down", kind=ConnectorErrorKind.TRANSIENT, retryable=True)

    monkeypatch.setattr(RSSConnector, "fetch_updates", boom_fetch)
    monkeypatch.setattr(MentionStore, "load_checkpoint", _async_none)
    monkeypatch.setattr(MentionStore, "save_checkpoint", _async_noop)

    outcome = await poll_rss_feed(FakeSession(), feed_url="https://example.com/feed.xml")  # type: ignore[arg-type]
    assert outcome.error is not None
    assert "transient" in outcome.error
    assert outcome.fetched == 0
    assert outcome.inserted == 0


@pytest.mark.asyncio
async def test_poll_success_path_inserts(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (FIXTURES / "sample.rss.xml").read_bytes()
    original_init = RSSConnector.__init__

    def patched_init(self, config):  # type: ignore[no-untyped-def]
        original_init(self, config)
        self._client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
        )

    inserted_rows: list = []

    async def fake_upsert(self, mentions, *, project_id=None):  # type: ignore[no-untyped-def]
        inserted_rows.extend(mentions)
        return len(mentions)

    monkeypatch.setattr(RSSConnector, "__init__", patched_init)
    monkeypatch.setattr(MentionStore, "load_checkpoint", _async_none)
    monkeypatch.setattr(MentionStore, "save_checkpoint", _async_noop)
    monkeypatch.setattr(MentionStore, "upsert_mentions", fake_upsert)

    outcome = await poll_rss_feed(FakeSession(), feed_url="https://example.com/feed.xml")  # type: ignore[arg-type]
    assert outcome.error is None
    assert outcome.fetched == 2
    assert outcome.inserted == 2
    assert len(inserted_rows) == 2


async def _async_none(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    return None


async def _async_noop(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    return None
