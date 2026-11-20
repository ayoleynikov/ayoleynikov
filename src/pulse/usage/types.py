"""Usage and cost domain types (Pydantic)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CostComponent(str, Enum):
    """Billable dimensions — prices come from config, never invented as vendor truth."""

    HTTP_REQUEST = "http_request"
    BYTE_DOWNLOADED = "byte_downloaded"
    BYTE_UPLOADED = "byte_uploaded"
    ITEM_COLLECTED = "item_collected"
    ITEM_ACCEPTED = "item_accepted"
    WORKER_MS = "worker_ms"
    STORAGE_BYTE = "storage_byte"
    NETWORK_BYTE = "network_byte"
    AI_TOKEN = "ai_token"
    RETRY = "retry"


class PricingUnit(str, Enum):
    PER_1 = "per_1"
    PER_1000 = "per_1000"
    PER_MB = "per_mb"
    PER_GB = "per_gb"


class UsageMetrics(BaseModel):
    """Counters recorded for one operation."""

    source: str
    operation: str
    organization_id: UUID | None = None
    project_id: UUID | None = None
    recorded_at: datetime | None = None

    http_requests: int = 0
    bytes_downloaded: int = 0
    bytes_uploaded: int = 0
    items_collected: int = 0
    items_accepted: int = 0
    items_rejected: int = 0
    items_duplicates: int = 0
    worker_time_ms: int = 0
    retries: int = 0
    storage_bytes: int = 0
    network_bytes: int = 0
    ai_tokens: int = 0
    extras: dict[str, Any] = Field(default_factory=dict)


class PricingRule(BaseModel):
    """One configurable unit price. Label must clarify provenance (fixture/operator)."""

    source: str
    cost_component: CostComponent
    unit: PricingUnit = PricingUnit.PER_1
    unit_price_usd: Decimal
    currency: str = "USD"
    pricing_label: str = "operator"
    notes: str | None = None
    is_active: bool = True


class CostLine(BaseModel):
    cost_component: CostComponent
    quantity: Decimal
    unit: PricingUnit
    unit_price_usd: Decimal
    amount_usd: Decimal
    pricing_label: str


class CostBreakdown(BaseModel):
    source: str
    operation: str
    organization_id: UUID | None = None
    project_id: UUID | None = None
    total_usd: Decimal
    pricing_label: str
    lines: list[CostLine] = Field(default_factory=list)
    disclaimer: str = (
        "Costs use operator/fixture pricing configuration only — "
        "not verified third-party API list prices."
    )


class UsageRecordView(BaseModel):
    id: UUID | None = None
    source: str
    operation: str
    organization_id: UUID | None = None
    project_id: UUID | None = None
    recorded_at: datetime
    http_requests: int = 0
    bytes_downloaded: int = 0
    bytes_uploaded: int = 0
    items_collected: int = 0
    items_accepted: int = 0
    items_rejected: int = 0
    items_duplicates: int = 0
    worker_time_ms: int = 0
    retries: int = 0
    storage_bytes: int = 0
    network_bytes: int = 0
    ai_tokens: int = 0
    cost_usd: Decimal | None = None
    pricing_label: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class CostRollup(BaseModel):
    group_by: str
    key: str
    organization_id: UUID | None = None
    project_id: UUID | None = None
    source: str | None = None
    total_cost_usd: Decimal
    total_items_accepted: int
    cost_per_1k_mentions_usd: Decimal | None = None
    cost_per_ai_analysis_usd: Decimal | None = None
    ai_analyses: int = 0
    record_count: int = 0
