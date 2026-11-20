"""Configurable pricing catalog — never hardcodes unverified vendor API prices as truth."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Sequence

from pulse.usage.types import CostComponent, PricingRule, PricingUnit


# Explicit fixture catalog for tests / local demos. These are NOT vendor list prices.
FIXTURE_PRICING_LABEL = "fixture"
FIXTURE_PRICING_NOTES = (
    "Synthetic fixture prices for tests and local demos only. "
    "Replace with operator-configured rates before production cost reporting."
)


def fixture_pricing_rules() -> list[PricingRule]:
    """Return labeled fixture prices — clearly not third-party truth."""
    # Flat illustrative rates across sources; operators must replace for real accounting.
    common: list[tuple[CostComponent, PricingUnit, str]] = [
        (CostComponent.HTTP_REQUEST, PricingUnit.PER_1, "0.0001000000"),
        (CostComponent.BYTE_DOWNLOADED, PricingUnit.PER_MB, "0.0100000000"),
        (CostComponent.ITEM_COLLECTED, PricingUnit.PER_1000, "0.0500000000"),
        (CostComponent.ITEM_ACCEPTED, PricingUnit.PER_1000, "0.1000000000"),
        (CostComponent.WORKER_MS, PricingUnit.PER_1000, "0.0010000000"),
        (CostComponent.RETRY, PricingUnit.PER_1, "0.0000500000"),
        (CostComponent.STORAGE_BYTE, PricingUnit.PER_GB, "0.0200000000"),
        (CostComponent.NETWORK_BYTE, PricingUnit.PER_GB, "0.0500000000"),
        (CostComponent.AI_TOKEN, PricingUnit.PER_1000, "0.0020000000"),
    ]
    sources = ("rss", "bluesky", "gdelt", "system", "*")
    rules: list[PricingRule] = []
    for source in sources:
        for component, unit, price in common:
            rules.append(
                PricingRule(
                    source=source,
                    cost_component=component,
                    unit=unit,
                    unit_price_usd=Decimal(price),
                    pricing_label=FIXTURE_PRICING_LABEL,
                    notes=FIXTURE_PRICING_NOTES,
                )
            )
    return rules


class PricingCatalog:
    """In-memory pricing lookup keyed by (source, component)."""

    def __init__(self, rules: Sequence[PricingRule] | None = None) -> None:
        self._rules: list[PricingRule] = [r for r in (rules or []) if r.is_active]

    @classmethod
    def from_fixture(cls) -> PricingCatalog:
        return cls(fixture_pricing_rules())

    def add(self, rule: PricingRule) -> None:
        if rule.is_active:
            self._rules.append(rule)

    def extend(self, rules: Iterable[PricingRule]) -> None:
        for rule in rules:
            self.add(rule)

    def list_rules(self, *, source: str | None = None) -> list[PricingRule]:
        if source is None:
            return list(self._rules)
        return [r for r in self._rules if r.source in (source, "*")]

    def resolve(self, source: str, component: CostComponent) -> PricingRule | None:
        """Prefer exact source match; fall back to wildcard ``*``."""
        exact: PricingRule | None = None
        wildcard: PricingRule | None = None
        for rule in self._rules:
            if rule.cost_component != component:
                continue
            if rule.source == source:
                exact = rule
            elif rule.source == "*":
                wildcard = rule
        return exact or wildcard

    @property
    def pricing_label(self) -> str:
        labels = {r.pricing_label for r in self._rules}
        if len(labels) == 1:
            return next(iter(labels))
        if not labels:
            return "none"
        return "mixed"
