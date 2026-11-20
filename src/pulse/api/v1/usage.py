"""Usage and cost API (Phase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from pulse.monitoring.metrics_registry import observe_connector_accounting, observe_usage_record
from pulse.usage.pricing import PricingCatalog, fixture_pricing_rules
from pulse.usage.recorder import get_usage_recorder, reset_usage_recorder
from pulse.usage.types import CostRollup, PricingRule, UsageMetrics, UsageRecordView

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageSummaryResponse(BaseModel):
    record_count: int
    http_requests: int
    bytes_downloaded: int
    items_collected: int
    items_accepted: int
    items_rejected: int
    items_duplicates: int
    worker_time_ms: int
    retries: int
    storage_bytes: int
    network_bytes: int
    ai_tokens: int
    total_cost_usd: str
    pricing_disclaimer: str


class RecordUsageRequest(BaseModel):
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
    price: bool = True


class LoadFixturePricingResponse(BaseModel):
    loaded: int
    pricing_label: str
    disclaimer: str


class PricingListResponse(BaseModel):
    rules: list[PricingRule]
    disclaimer: str = (
        "Listed prices are operator/fixture configuration only — "
        "not verified third-party API list prices."
    )


class RollupResponse(BaseModel):
    group_by: str
    rollups: list[CostRollup]
    disclaimer: str = (
        "Costs use operator/fixture pricing configuration only — "
        "not verified third-party API list prices."
    )


@router.get("", response_model=UsageSummaryResponse)
async def usage_summary(
    source: str | None = None,
    organization_id: UUID | None = None,
    project_id: UUID | None = None,
) -> UsageSummaryResponse:
    recorder = get_usage_recorder()
    return UsageSummaryResponse(**recorder.summary(
        source=source,
        organization_id=organization_id,
        project_id=project_id,
    ))


@router.get("/records", response_model=list[UsageRecordView])
async def list_usage_records(
    source: str | None = None,
    organization_id: UUID | None = None,
    project_id: UUID | None = None,
) -> list[UsageRecordView]:
    return get_usage_recorder().list_records(
        source=source,
        organization_id=organization_id,
        project_id=project_id,
    )


@router.post("/records", response_model=UsageRecordView)
async def create_usage_record(body: RecordUsageRequest) -> UsageRecordView:
    recorder = get_usage_recorder()
    view = recorder.record(
        UsageMetrics(
            source=body.source,
            operation=body.operation,
            organization_id=body.organization_id,
            project_id=body.project_id,
            recorded_at=body.recorded_at,
            http_requests=body.http_requests,
            bytes_downloaded=body.bytes_downloaded,
            bytes_uploaded=body.bytes_uploaded,
            items_collected=body.items_collected,
            items_accepted=body.items_accepted,
            items_rejected=body.items_rejected,
            items_duplicates=body.items_duplicates,
            worker_time_ms=body.worker_time_ms,
            retries=body.retries,
            storage_bytes=body.storage_bytes,
            network_bytes=body.network_bytes,
            ai_tokens=body.ai_tokens,
            extras=body.extras,
        ),
        price=body.price,
    )
    observe_connector_accounting(
        source=view.source,
        operation=view.operation,
        http_requests=view.http_requests,
        bytes_downloaded=view.bytes_downloaded,
        items_fetched=view.items_collected,
        retries=view.retries,
    )
    observe_usage_record(
        source=view.source,
        operation=view.operation,
        cost_usd=float(view.cost_usd) if view.cost_usd is not None else None,
        pricing_label=view.pricing_label,
        ai_tokens=view.ai_tokens,
    )
    return view


@router.get("/costs", response_model=RollupResponse)
async def usage_costs(
    group_by: Literal["source", "project", "organization"] = Query(default="source"),
) -> RollupResponse:
    try:
        rollups = get_usage_recorder().rollups(group_by=group_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RollupResponse(group_by=group_by, rollups=rollups)


@router.get("/pricing", response_model=PricingListResponse)
async def list_pricing() -> PricingListResponse:
    return PricingListResponse(rules=list(get_usage_recorder().pricing_rules()))


@router.post("/pricing/fixture", response_model=LoadFixturePricingResponse)
async def load_fixture_pricing() -> LoadFixturePricingResponse:
    """Load synthetic fixture prices for demos/tests — not vendor truth."""
    catalog = PricingCatalog.from_fixture()
    reset_usage_recorder(catalog)
    rules = fixture_pricing_rules()
    return LoadFixturePricingResponse(
        loaded=len(rules),
        pricing_label=catalog.pricing_label,
        disclaimer=(
            "Fixture prices loaded. These are synthetic and must not be treated "
            "as verified third-party API list prices."
        ),
    )


class AddPricingRuleRequest(BaseModel):
    rule: PricingRule


@router.post("/pricing", response_model=PricingListResponse)
async def add_pricing_rule(body: AddPricingRuleRequest) -> PricingListResponse:
    """Register an operator-configured price (explicit provenance via pricing_label)."""
    recorder = get_usage_recorder()
    recorder.catalog.add(body.rule)
    return PricingListResponse(rules=list(recorder.pricing_rules()))
