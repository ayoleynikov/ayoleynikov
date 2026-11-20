"""Configured RSS/Atom feed sources to poll."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pulse.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FeedSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-scoped public feed URL scheduled for RSS polling."""

    __tablename__ = "feed_sources"
    __table_args__ = (
        UniqueConstraint("project_id", "feed_url", name="uq_feed_sources_project_url"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)

    def __repr__(self) -> str:
        return f"<FeedSource name={self.name!r} url={self.feed_url!r}>"
