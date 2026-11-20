"""Usage recording and cost engine tests — fixture prices only."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from pulse.connectors.types import RequestAccounting
from pulse.usage import (
    FIXTURE_PRICING_LABEL,
    CostComponent,
    PricingCatalog,
    PricingRule,
    UsageMetrics,
    UsageRecorder,
    calculate_cost,
    fixture_pricing_rules,
    rollup_costs,
)
from pulse.usage.pricing import PricingUnit
from pulse.usage.types import UsageRecordView
from datetime import datetime, timezone


def test_fixture_pricing_is_labeled_not_vendor_truth() -> None:
    rules = fixture_pricing_rules()
    assert rules
    assert all(r.pricing_label == FIXTURE_PRICING_LABEL for r in rules)
    assert all(r.notes and "Synthetic" in r.notes for r in rules)


def test_calculate_cost_with_fixture_prices() -> None:
    catalog = PricingCatalog.from_fixture()
    metrics = UsageMetrics(
        source="gdelt",
        operation="search",
        http_requests=10,
        bytes_downloaded=2 * 1024 * 1024,  # 2 MiB
        items_collected=500,
        items_accepted=400,
        worker_time_ms=2000,
        retries=3,
        ai_tokens=1000,
    )
    breakdown = calculate_cost(metrics, catalog)
    assert breakdown.pricing_label == FIXTURE_PRICING_LABEL
    assert breakdown.total_usd > 0
    assert "not verified" in breakdown.disclaimer.lower()
    components = {line.cost_component for line in breakdown.lines}
    assert CostComponent.HTTP_REQUEST in components
    assert CostComponent.ITEM_ACCEPTED in components
    assert CostComponent.AI_TOKEN in components


def test_empty_catalog_yields_zero_cost() -> None:
    catalog = PricingCatalog([])
    metrics = UsageMetrics(source="rss", operation="fetch", http_requests=5, items_accepted=10)
    breakdown = calculate_cost(metrics, catalog)
    assert breakdown.total_usd == Decimal("0E-8") or breakdown.total_usd == 0
    assert breakdown.lines == []


def test_operator_price_overrides_wildcard() -> None:
    catalog = PricingCatalog(
        [
            PricingRule(
                source="*",
                cost_component=CostComponent.HTTP_REQUEST,
                unit=PricingUnit.PER_1,
                unit_price_usd=Decimal("1.00"),
                pricing_label="operator",
            ),
            PricingRule(
                source="rss",
                cost_component=CostComponent.HTTP_REQUEST,
                unit=PricingUnit.PER_1,
                unit_price_usd=Decimal("0.25"),
                pricing_label="operator",
            ),
        ]
    )
    breakdown = calculate_cost(
        UsageMetrics(source="rss", operation="fetch", http_requests=4),
        catalog,
    )
    assert breakdown.total_usd == Decimal("1.00000000")
    assert breakdown.lines[0].unit_price_usd == Decimal("0.25")


def test_recorder_from_accounting_and_rollups() -> None:
    recorder = UsageRecorder(PricingCatalog.from_fixture())
    org = uuid4()
    project = uuid4()
    accounting = RequestAccounting(
        http_requests=2,
        bytes_downloaded=1024,
        items_fetched=50,
        retries=1,
    )
    view = recorder.record_from_accounting(
        accounting,
        source="bluesky",
        operation="stream",
        organization_id=org,
        project_id=project,
        items_accepted=40,
        items_rejected=5,
        items_duplicates=5,
        worker_time_ms=100,
    )
    assert view.cost_usd is not None and view.cost_usd > 0
    assert view.pricing_label == FIXTURE_PRICING_LABEL
    assert view.items_collected == 50

    # second project under same org
    recorder.record(
        UsageMetrics(
            source="gdelt",
            operation="search",
            organization_id=org,
            project_id=uuid4(),
            http_requests=1,
            items_accepted=1000,
            ai_tokens=500,
        )
    )

    by_source = recorder.rollups(group_by="source")
    assert {r.key for r in by_source} >= {"bluesky", "gdelt"}
    gdelt = next(r for r in by_source if r.key == "gdelt")
    assert gdelt.cost_per_1k_mentions_usd is not None
    assert gdelt.total_items_accepted == 1000

    by_org = recorder.rollups(group_by="organization")
    assert len(by_org) == 1
    assert by_org[0].key == str(org)

    summary = recorder.summary(organization_id=org)
    assert summary["record_count"] == 2
    assert summary["items_accepted"] == 1040


def test_cost_per_1k_and_per_ai_analysis() -> None:
    now = datetime.now(timezone.utc)
    records = [
        UsageRecordView(
            id=uuid4(),
            source="gdelt",
            operation="search",
            recorded_at=now,
            items_accepted=500,
            cost_usd=Decimal("2.00"),
        ),
        UsageRecordView(
            id=uuid4(),
            source="gdelt",
            operation="ai.classify",
            recorded_at=now,
            items_accepted=0,
            ai_tokens=100,
            cost_usd=Decimal("0.50"),
        ),
        UsageRecordView(
            id=uuid4(),
            source="gdelt",
            operation="ai.classify",
            recorded_at=now,
            items_accepted=0,
            ai_tokens=100,
            cost_usd=Decimal("0.50"),
        ),
    ]
    rollups = rollup_costs(records, group_by="source")
    assert len(rollups) == 1
    r = rollups[0]
    assert r.total_cost_usd == Decimal("3.00000000")
    assert r.cost_per_1k_mentions_usd == Decimal("6.00000000")
    assert r.ai_analyses == 2
    assert r.cost_per_ai_analysis_usd == Decimal("0.50000000")


def test_unsupported_group_by_raises() -> None:
    with pytest.raises(ValueError, match="unsupported group_by"):
        rollup_costs([], group_by="tenant")
