"""Usage records and configurable source cost pricing."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pulse.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UsageRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted usage snapshot for a connector/worker operation."""

    __tablename__ = "usage_records"

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    http_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_uploaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    items_collected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    network_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ai_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    pricing_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")

    def __repr__(self) -> str:
        return f"<UsageRecord source={self.source!r} operation={self.operation!r}>"


class SourceCost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Operator-configured unit prices — never treated as verified vendor truth."""

    __tablename__ = "source_costs"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "cost_component",
            "pricing_label",
            name="uq_source_costs_source_component_label",
        ),
    )

    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cost_component: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="per_1")
    unit_price_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    pricing_label: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="operator",
        doc="e.g. fixture, operator-configured — not vendor-authoritative",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SourceCost source={self.source!r} component={self.cost_component!r} "
            f"label={self.pricing_label!r}>"
        )
