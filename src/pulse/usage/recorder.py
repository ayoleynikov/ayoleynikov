"""In-memory / service-layer usage recorder with optional cost attachment."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID, uuid4

from pulse.connectors.types import RequestAccounting
from pulse.usage.cost_engine import calculate_cost, rollup_costs
from pulse.usage.pricing import PricingCatalog
from pulse.usage.types import (
    CostBreakdown,
    CostRollup,
    PricingRule,
    UsageMetrics,
    UsageRecordView,
)


class UsageRecorder:
    """Records usage metrics, optionally prices them, and supports rollups.

    Process-local store for API/tests; Postgres ``usage_records`` is the durable table.
    """

    def __init__(self, catalog: PricingCatalog | None = None) -> None:
        self.catalog = catalog or PricingCatalog()
        self._records: list[UsageRecordView] = []

    def set_catalog(self, catalog: PricingCatalog) -> None:
        self.catalog = catalog

    def record(self, metrics: UsageMetrics, *, price: bool = True) -> UsageRecordView:
        recorded_at = metrics.recorded_at or datetime.now(timezone.utc)
        cost: CostBreakdown | None = None
        cost_usd = None
        pricing_label = None
        if price and self.catalog.list_rules():
            cost = calculate_cost(metrics, self.catalog)
            cost_usd = cost.total_usd
            pricing_label = cost.pricing_label

        view = UsageRecordView(
            id=uuid4(),
            source=metrics.source,
            operation=metrics.operation,
            organization_id=metrics.organization_id,
            project_id=metrics.project_id,
            recorded_at=recorded_at,
            http_requests=metrics.http_requests,
            bytes_downloaded=metrics.bytes_downloaded,
            bytes_uploaded=metrics.bytes_uploaded,
            items_collected=metrics.items_collected,
            items_accepted=metrics.items_accepted,
            items_rejected=metrics.items_rejected,
            items_duplicates=metrics.items_duplicates,
            worker_time_ms=metrics.worker_time_ms,
            retries=metrics.retries,
            storage_bytes=metrics.storage_bytes,
            network_bytes=metrics.network_bytes
            or (metrics.bytes_downloaded + metrics.bytes_uploaded),
            ai_tokens=metrics.ai_tokens,
            cost_usd=cost_usd,
            pricing_label=pricing_label,
            extras={
                **metrics.extras,
                **({"cost_lines": [line.model_dump(mode="json") for line in cost.lines]} if cost else {}),
            },
        )
        self._records.append(view)
        return view

    def record_from_accounting(
        self,
        accounting: RequestAccounting,
        *,
        source: str,
        operation: str,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
        items_accepted: int = 0,
        items_rejected: int = 0,
        items_duplicates: int = 0,
        worker_time_ms: int = 0,
        storage_bytes: int = 0,
        ai_tokens: int = 0,
        extras: dict | None = None,
    ) -> UsageRecordView:
        """Bridge connector ``RequestAccounting`` into usage tracking."""
        return self.record(
            UsageMetrics(
                source=source,
                operation=operation,
                organization_id=organization_id,
                project_id=project_id,
                http_requests=accounting.http_requests,
                bytes_downloaded=accounting.bytes_downloaded,
                items_collected=accounting.items_fetched,
                items_accepted=items_accepted,
                items_rejected=items_rejected,
                items_duplicates=items_duplicates,
                worker_time_ms=worker_time_ms,
                retries=accounting.retries,
                storage_bytes=storage_bytes,
                network_bytes=accounting.bytes_downloaded,
                ai_tokens=ai_tokens,
                extras={
                    **(extras or {}),
                    "not_modified": accounting.not_modified,
                },
            )
        )

    def list_records(
        self,
        *,
        source: str | None = None,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> list[UsageRecordView]:
        rows = self._records
        if source is not None:
            rows = [r for r in rows if r.source == source]
        if organization_id is not None:
            rows = [r for r in rows if r.organization_id == organization_id]
        if project_id is not None:
            rows = [r for r in rows if r.project_id == project_id]
        return list(rows)

    def summary(
        self,
        *,
        source: str | None = None,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> dict:
        rows = self.list_records(
            source=source,
            organization_id=organization_id,
            project_id=project_id,
        )
        total_cost = sum((r.cost_usd or 0) for r in rows)
        return {
            "record_count": len(rows),
            "http_requests": sum(r.http_requests for r in rows),
            "bytes_downloaded": sum(r.bytes_downloaded for r in rows),
            "items_collected": sum(r.items_collected for r in rows),
            "items_accepted": sum(r.items_accepted for r in rows),
            "items_rejected": sum(r.items_rejected for r in rows),
            "items_duplicates": sum(r.items_duplicates for r in rows),
            "worker_time_ms": sum(r.worker_time_ms for r in rows),
            "retries": sum(r.retries for r in rows),
            "storage_bytes": sum(r.storage_bytes for r in rows),
            "network_bytes": sum(r.network_bytes for r in rows),
            "ai_tokens": sum(r.ai_tokens for r in rows),
            "total_cost_usd": str(total_cost),
            "pricing_disclaimer": (
                "Costs use operator/fixture pricing configuration only — "
                "not verified third-party API list prices."
            ),
        }

    def rollups(self, *, group_by: str = "source") -> list[CostRollup]:
        return rollup_costs(self._records, group_by=group_by)

    def pricing_rules(self) -> Sequence[PricingRule]:
        return self.catalog.list_rules()


# Process-local default used by the API layer (tests inject fixtures via reset).
_default_recorder: UsageRecorder | None = None


def get_usage_recorder() -> UsageRecorder:
    global _default_recorder
    if _default_recorder is None:
        _default_recorder = UsageRecorder()
    return _default_recorder


def reset_usage_recorder(catalog: PricingCatalog | None = None) -> UsageRecorder:
    """Replace the process-local recorder (used by tests)."""
    global _default_recorder
    _default_recorder = UsageRecorder(catalog)
    return _default_recorder
