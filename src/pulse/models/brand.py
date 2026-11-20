"""Brand monitoring models — brands, aliases, competitors, queries, matches."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pulse.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_brands_project_slug"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    aliases: Mapped[list[BrandAlias]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    queries: Mapped[list[MonitoringQuery]] = relationship(
        back_populates="brand",
        cascade="all, delete-orphan",
    )


class BrandAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brand_aliases"
    __table_args__ = (
        UniqueConstraint("brand_id", "alias", name="uq_brand_aliases_brand_alias"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    brand: Mapped[Brand] = relationship(back_populates="aliases")


class Competitor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "competitors"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "brand_id",
            "competitor_brand_id",
            name="uq_competitors_project_brand_competitor",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competitor_brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonitoringQuery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Boolean monitoring query — AST stored as JSON; never executed as SQL."""

    __tablename__ = "monitoring_queries"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    ast_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    brand: Mapped[Brand | None] = relationship(back_populates="queries")


class MentionMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mention_matches"
    __table_args__ = (
        UniqueConstraint("mention_id", "brand_id", name="uq_mention_matches_mention_brand"),
    )

    mention_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_queries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    match_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """L4 semantic/event clustering scaffold — distinct from mention rows."""

    __tablename__ = "event_clusters"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    cluster_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scaffold")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )


class MentionClusterMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Membership of a mention in an event cluster (L4 scaffold)."""

    __tablename__ = "mention_cluster_members"
    __table_args__ = (
        UniqueConstraint("cluster_id", "mention_id", name="uq_cluster_member_cluster_mention"),
    )

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mention_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
