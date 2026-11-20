"""Shared checkpoint load/save used by RSS, Bluesky, and future connectors."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.connectors.types import CheckpointCursor
from pulse.models.checkpoint import ConnectorCheckpoint


class CheckpointService:
    """Postgres-backed connector cursors — advance only after durable work."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load(self, connector: str, source_key: str) -> CheckpointCursor | None:
        stmt = select(ConnectorCheckpoint).where(
            ConnectorCheckpoint.connector == connector,
            ConnectorCheckpoint.source_key == source_key,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return row_to_cursor(row)

    async def save(
        self,
        cursor: CheckpointCursor,
        *,
        project_id: uuid.UUID | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        cursor_data = {
            **cursor.extra,
            "seen_external_ids": cursor.seen_external_ids,
        }
        values = {
            "id": uuid.uuid4(),
            "connector": cursor.connector,
            "source_key": cursor.source_key,
            "project_id": project_id,
            "etag": cursor.etag,
            "last_modified": cursor.last_modified,
            "cursor_token": cursor.cursor_token,
            "cursor_data": cursor_data,
            "last_polled_at": now,
            "last_success_at": now if success else None,
            "last_error": error,
        }
        stmt = insert(ConnectorCheckpoint).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_checkpoint_connector_source",
            set_={
                "project_id": project_id,
                "etag": cursor.etag,
                "last_modified": cursor.last_modified,
                "cursor_token": cursor.cursor_token,
                "cursor_data": cursor_data,
                "last_polled_at": now,
                "last_success_at": now if success else ConnectorCheckpoint.last_success_at,
                "last_error": error,
                "updated_at": now,
            },
        )
        await self.session.execute(stmt)

    async def recover(self, connector: str, source_key: str) -> CheckpointCursor | None:
        """Alias for load — used by recovery tests and worker boot paths."""
        return await self.load(connector, source_key)


def row_to_cursor(row: ConnectorCheckpoint) -> CheckpointCursor:
    data: dict[str, Any] = dict(row.cursor_data or {})
    return CheckpointCursor(
        connector=row.connector,
        source_key=row.source_key,
        etag=row.etag,
        last_modified=row.last_modified,
        cursor_token=row.cursor_token,
        seen_external_ids=list(data.get("seen_external_ids") or []),
        extra={k: v for k, v in data.items() if k != "seen_external_ids"},
    )
