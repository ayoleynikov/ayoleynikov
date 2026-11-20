"""Cost calculation and rollups from usage metrics + configurable pricing."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence
from uuid import UUID

from pulse.usage.pricing import PricingCatalog
from pulse.usage.types import (
    CostBreakdown,
    CostComponent,
    CostLine,
    CostRollup,
    PricingUnit,
    UsageMetrics,
    UsageRecordView,
)

_QUANT = Decimal("0.00000001")
_ZERO = Decimal("0")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _quantity_for(component: CostComponent, metrics: UsageMetrics) -> Decimal:
    network = metrics.network_bytes or (metrics.bytes_downloaded + metrics.bytes_uploaded)
    mapping = {
        CostComponent.HTTP_REQUEST: metrics.http_requests,
        CostComponent.BYTE_DOWNLOADED: metrics.bytes_downloaded,
        CostComponent.BYTE_UPLOADED: metrics.bytes_uploaded,
        CostComponent.ITEM_COLLECTED: metrics.items_collected,
        CostComponent.ITEM_ACCEPTED: metrics.items_accepted,
        CostComponent.WORKER_MS: metrics.worker_time_ms,
        CostComponent.STORAGE_BYTE: metrics.storage_bytes,
        CostComponent.NETWORK_BYTE: network,
        CostComponent.AI_TOKEN: metrics.ai_tokens,
        CostComponent.RETRY: metrics.retries,
    }
    return Decimal(mapping.get(component, 0))


def _billable_units(quantity: Decimal, unit: PricingUnit) -> Decimal:
    if unit == PricingUnit.PER_1:
        return quantity
    if unit == PricingUnit.PER_1000:
        return quantity / Decimal("1000")
    if unit == PricingUnit.PER_MB:
        return quantity / Decimal(1024 * 1024)
    if unit == PricingUnit.PER_GB:
        return quantity / Decimal(1024 * 1024 * 1024)
    return quantity


def calculate_cost(
    metrics: UsageMetrics,
    catalog: PricingCatalog,
) -> CostBreakdown:
    """Compute cost for one usage snapshot using the provided catalog only."""
    lines: list[CostLine] = []
    total = _ZERO
    labels: set[str] = set()

    for component in CostComponent:
        rule = catalog.resolve(metrics.source, component)
        if rule is None:
            continue
        raw_qty = _quantity_for(component, metrics)
        if raw_qty <= 0:
            continue
        billable = _billable_units(raw_qty, rule.unit)
        amount = _quantize(billable * rule.unit_price_usd)
        lines.append(
            CostLine(
                cost_component=component,
                quantity=_quantize(raw_qty),
                unit=rule.unit,
                unit_price_usd=rule.unit_price_usd,
                amount_usd=amount,
                pricing_label=rule.pricing_label,
            )
        )
        total += amount
        labels.add(rule.pricing_label)

    if len(labels) == 1:
        pricing_label = next(iter(labels))
    elif labels:
        pricing_label = "mixed"
    else:
        pricing_label = catalog.pricing_label

    return CostBreakdown(
        source=metrics.source,
        operation=metrics.operation,
        organization_id=metrics.organization_id,
        project_id=metrics.project_id,
        total_usd=_quantize(total),
        pricing_label=pricing_label,
        lines=lines,
    )


def _per_1k(total_cost: Decimal, items: int) -> Decimal | None:
    if items <= 0:
        return None
    return _quantize(total_cost * Decimal("1000") / Decimal(items))


def _per_ai(total_ai_cost: Decimal, analyses: int) -> Decimal | None:
    if analyses <= 0:
        return None
    return _quantize(total_ai_cost / Decimal(analyses))


def _group_key(record: UsageRecordView, group_by: str) -> str:
    if group_by == "source":
        return record.source
    if group_by == "project":
        return str(record.project_id) if record.project_id else "unassigned"
    if group_by == "organization":
        return str(record.organization_id) if record.organization_id else "unassigned"
    msg = f"unsupported group_by: {group_by}"
    raise ValueError(msg)


def rollup_costs(
    records: Sequence[UsageRecordView],
    *,
    group_by: str = "source",
) -> list[CostRollup]:
    """Aggregate costs by source, project, or organization."""
    if group_by not in {"source", "project", "organization"}:
        msg = f"unsupported group_by: {group_by}"
        raise ValueError(msg)

    buckets: dict[str, list[UsageRecordView]] = defaultdict(list)
    for record in records:
        buckets[_group_key(record, group_by)].append(record)

    rollups: list[CostRollup] = []
    for key, group in sorted(buckets.items()):
        total_cost = _quantize(sum((r.cost_usd or _ZERO for r in group), _ZERO))
        items = sum(r.items_accepted for r in group)
        ai_records = [r for r in group if r.ai_tokens > 0]
        analyses = len(ai_records)
        ai_cost = _quantize(sum((r.cost_usd or _ZERO for r in ai_records), _ZERO))

        org_id: UUID | None = None
        project_id: UUID | None = None
        source: str | None = None
        if group_by == "organization":
            org_id = group[0].organization_id
        elif group_by == "project":
            project_id = group[0].project_id
            org_id = group[0].organization_id
        else:
            source = key

        rollups.append(
            CostRollup(
                group_by=group_by,
                key=key,
                organization_id=org_id,
                project_id=project_id,
                source=source,
                total_cost_usd=total_cost,
                total_items_accepted=items,
                cost_per_1k_mentions_usd=_per_1k(total_cost, items),
                cost_per_ai_analysis_usd=_per_ai(ai_cost, analyses),
                ai_analyses=analyses,
                record_count=len(group),
            )
        )
    return rollups
