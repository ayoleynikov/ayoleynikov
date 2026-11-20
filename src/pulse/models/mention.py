"""Postgres interim storage for normalized mentions (pre-ClickHouse)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pulse.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Mention(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Normalized mention row — Phase 2 minimal path into storage."""

    __tablename__ = "mentions"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_mentions_source_external_id"),
    )

    mention_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engagement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    source_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Mention source={self.source!r} external_id={self.external_id!r}>"
