"""Dead-letter records for exhausted / permanent task failures."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pulse.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DeadLetter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Observable failed task after retries are exhausted (or permanent failure)."""

    __tablename__ = "dead_letters"

    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    queue: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    args_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    kwargs_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    exception_type: Mapped[str] = mapped_column(String(255), nullable=False)
    exception_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<DeadLetter task={self.task_name!r} status={self.status!r}>"
