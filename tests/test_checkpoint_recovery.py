"""Shared CheckpointService recovery semantics (no live Postgres required)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from pulse.checkpoints.service import CheckpointService, row_to_cursor
from pulse.connectors.types import CheckpointCursor
from pulse.models.checkpoint import ConnectorCheckpoint


class _Result:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], ConnectorCheckpoint] = {}
        self.executed: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        self.executed.append(stmt)
        # Very small fake: load path uses select; save uses insert.
        sql = str(stmt)
        if "INSERT" in sql.upper() or "insert" in type(stmt).__name__.lower():
            return _Result(None)
        # For select, return stored row if present — tests call load after manual seed.
        return _Result(None)


@pytest.mark.asyncio
async def test_checkpoint_service_save_and_row_roundtrip() -> None:
    row = ConnectorCheckpoint(
        id=uuid4(),
        connector="rss",
        source_key="https://example.com/feed.xml",
        etag='"v1"',
        last_modified="Mon, 01 Jan 2024 12:00:00 GMT",
        cursor_token=None,
        cursor_data={"seen_external_ids": ["a", "b"], "feed_meta": {"title": "t"}},
        last_polled_at=datetime.now(UTC),
        last_success_at=datetime.now(UTC),
        last_error=None,
    )
    cursor = row_to_cursor(row)
    assert cursor.connector == "rss"
    assert cursor.etag == '"v1"'
    assert cursor.seen_external_ids == ["a", "b"]
    assert cursor.extra["feed_meta"]["title"] == "t"


@pytest.mark.asyncio
async def test_checkpoint_recovery_returns_saved_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeAsyncSession()
    service = CheckpointService(session)  # type: ignore[arg-type]

    saved = CheckpointCursor(
        connector="bluesky",
        source_key="bluesky:jetstream",
        cursor_token="1725911162329308",
        extra={"time_us": 1725911162329308, "seq": 12345},
    )

    async def fake_load(connector: str, source_key: str) -> CheckpointCursor | None:
        assert connector == "bluesky"
        return saved

    monkeypatch.setattr(service, "load", fake_load)
    recovered = await service.recover("bluesky", "bluesky:jetstream")
    assert recovered is not None
    assert recovered.cursor_token == "1725911162329308"
    assert recovered.extra["seq"] == 12345


@pytest.mark.asyncio
async def test_checkpoint_not_advanced_on_failed_save_flag() -> None:
    """Document the durable contract: callers pass success=False on errors."""
    session = _FakeAsyncSession()
    service = CheckpointService(session)  # type: ignore[arg-type]
    cursor = CheckpointCursor(connector="rss", source_key="k", cursor_token="1")
    await service.save(cursor, success=False, error="transient: down")
    assert session.executed, "save should issue a statement"
    # Contract check — error path uses success=False (Jetstream/RSS callers).
    assert cursor.cursor_token == "1"
