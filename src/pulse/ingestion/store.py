"""Persist normalized mentions and connector checkpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.checkpoints.service import CheckpointService
from pulse.connectors.rss.connector import RSSConnector
from pulse.connectors.rss.config import RSSConnectorConfig
from pulse.connectors.types import CheckpointCursor, ConnectorError, NormalizedMention
from pulse.logging import get_logger
from pulse.models.mention import Mention

logger = get_logger(__name__)


class PollOutcome(BaseModel):
    """Result of one RSS poll cycle — never a silent empty success on failure."""

    source_key: str
    feed_url: str
    fetched: int
    inserted: int
    not_modified: bool = False
    accounting: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class MentionStore:
    """Async Postgres store for mentions + checkpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.checkpoints = CheckpointService(session)

    async def load_checkpoint(self, connector: str, source_key: str) -> CheckpointCursor | None:
        return await self.checkpoints.load(connector, source_key)

    async def save_checkpoint(
        self,
        cursor: CheckpointCursor,
        *,
        project_id: uuid.UUID | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        await self.checkpoints.save(
            cursor,
            project_id=project_id,
            success=success,
            error=error,
        )

    async def upsert_mentions(
        self,
        mentions: list[NormalizedMention],
        *,
        project_id: uuid.UUID | None = None,
    ) -> int:
        if not mentions:
            return 0
        rows = []
        for mention in mentions:
            m = mention.ensure_hashes()
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "mention_id": m.mention_id,
                    "source": m.source,
                    "external_id": m.external_id,
                    "source_url": m.source_url,
                    "author_id": m.author_id,
                    "author_name": m.author_name,
                    "content": m.content,
                    "title": m.title,
                    "language": m.language,
                    "published_at": m.published_at,
                    "collected_at": m.collected_at,
                    "engagement": m.engagement,
                    "metadata": m.metadata,
                    "content_hash": m.content_hash,
                    "canonical_url": m.canonical_url,
                    "source_version": m.source_version,
                    "project_id": project_id,
                    "deleted_at": None,
                }
            )
        insert_stmt = insert(Mention).values(rows)
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_mentions_source_external_id",
            set_={
                "content": excluded.content,
                "title": excluded.title,
                "source_url": excluded.source_url,
                "canonical_url": excluded.canonical_url,
                "content_hash": excluded.content_hash,
                "metadata": excluded["metadata"],
                "engagement": excluded.engagement,
                "collected_at": excluded.collected_at,
                "published_at": excluded.published_at,
                "source_version": excluded.source_version,
                "deleted_at": None,
                "updated_at": datetime.now(UTC),
            },
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def mark_deleted(
        self,
        *,
        source: str,
        external_id: str,
        deleted_at: datetime | None = None,
    ) -> bool:
        """Soft-delete a mention (Bluesky delete events). Returns True if a row was updated."""
        when = deleted_at or datetime.now(UTC)
        stmt = (
            update(Mention)
            .where(
                Mention.source == source,
                Mention.external_id == external_id,
                Mention.deleted_at.is_(None),
            )
            .values(deleted_at=when, updated_at=when)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0) > 0


async def poll_rss_feed(
    session: AsyncSession,
    *,
    feed_url: str,
    project_id: uuid.UUID | None = None,
    source_key: str | None = None,
    user_agent: str | None = None,
) -> PollOutcome:
    """Run one RSS poll: fetch → store mentions → persist checkpoint.

    Failures raise or return ``error`` set — never pretends success with empty data
    when the connector failed.
    """
    config_kwargs: dict[str, Any] = {"feed_url": feed_url}
    if source_key:
        config_kwargs["source_key"] = source_key
    if user_agent:
        config_kwargs["user_agent"] = user_agent
    config = RSSConnectorConfig.model_validate(config_kwargs)
    connector = RSSConnector(config)
    store = MentionStore(session)
    key = connector.source_key()

    try:
        cursor = await store.load_checkpoint(connector.name, key)
        result = await connector.fetch_updates(cursor=cursor)
        inserted = await store.upsert_mentions(result.mentions, project_id=project_id)
        if result.next_cursor is not None:
            await store.save_checkpoint(
                result.next_cursor,
                project_id=project_id,
                success=True,
                error=None,
            )
        await session.commit()
        logger.info(
            "rss_poll_complete",
            extra={
                "source_key": key,
                "fetched": len(result.mentions),
                "inserted": inserted,
                "not_modified": result.not_modified,
            },
        )
        return PollOutcome(
            source_key=key,
            feed_url=feed_url,
            fetched=len(result.mentions),
            inserted=inserted,
            not_modified=result.not_modified,
            accounting=result.accounting.model_dump(),
        )
    except ConnectorError as exc:
        await session.rollback()
        try:
            store = MentionStore(session)
            existing = await store.load_checkpoint("rss", key)
            cursor = existing or CheckpointCursor(connector="rss", source_key=key)
            await store.save_checkpoint(
                cursor,
                project_id=project_id,
                success=False,
                error=str(exc),
            )
            await session.commit()
        except Exception:  # noqa: BLE001 — best-effort error persistence
            await session.rollback()
            logger.exception("failed_to_persist_checkpoint_error", extra={"source_key": key})
        logger.error(
            "rss_poll_failed",
            extra={"source_key": key, "error": str(exc), "kind": exc.kind.value},
        )
        return PollOutcome(
            source_key=key,
            feed_url=feed_url,
            fetched=0,
            inserted=0,
            error=f"{exc.kind.value}: {exc}",
        )
    finally:
        await connector.close()
