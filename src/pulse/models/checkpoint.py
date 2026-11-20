"""Connector checkpoint persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pulse.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConnectorCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-source connector cursor (ETag, Last-Modified, seen IDs, opaque token)."""

    __tablename__ = "connector_checkpoints"
    __table_args__ = (
        UniqueConstraint("connector", "source_key", name="uq_checkpoint_connector_source"),
    )

    connector: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cursor_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ConnectorCheckpoint {self.connector}:{self.source_key}>"
