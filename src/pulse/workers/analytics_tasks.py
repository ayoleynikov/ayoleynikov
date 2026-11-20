"""Celery tasks for GDELT fetch + ClickHouse analytics sink."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from pulse.clickhouse.client import get_clickhouse_client
from pulse.clickhouse.sink import AnalyticsSink
from pulse.connectors.gdelt.connector import GDELTConnector
from pulse.connectors.types import SearchQuery
from pulse.ingestion.normalize import normalize_mention
from pulse.matching.matcher import BrandMatchResult
from pulse.workers.base_task import PulseTask
from pulse.workers.celery_app import celery_app
from pulse.workers.retry import PermanentTaskError, TransientTaskError


def _run_async(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.analytics_tasks.search_gdelt",
)
def search_gdelt(
    self: PulseTask,
    query: str,
    *,
    max_records: int = 25,
    timespan: str | None = "24h",
) -> dict[str, Any]:
    """Bounded GDELT DOC search — real HTTP; errors surface (no fake articles)."""

    async def _run() -> dict[str, Any]:
        connector = GDELTConnector(
            {"query": query, "max_records": max_records, "timespan": timespan}
        )
        try:
            result = await connector.search(SearchQuery(query=query, limit=max_records))
            return {
                "status": "ok",
                "stage": "source.fetch",
                "connector": "gdelt",
                "count": len(result.mentions),
                "mentions": [m.model_dump(mode="json") for m in result.mentions],
                "accounting": result.accounting.model_dump(),
                "exhausted": result.exhausted,
            }
        finally:
            await connector.close()

    try:
        return _run_async(_run())
    except Exception as exc:  # noqa: BLE001
        raise TransientTaskError(str(exc)) from exc


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.analytics_tasks.sink_to_clickhouse",
)
def sink_to_clickhouse(
    self: PulseTask,
    mentions: list[dict[str, Any]] | None = None,
    matches: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Sink normalized mentions (+ optional matches) to ClickHouse after matching."""
    if not project_id:
        raise PermanentTaskError("project_id required for tenant-scoped analytics sink")
    mentions = mentions or []
    normalized = [normalize_mention(m) for m in mentions]
    client = get_clickhouse_client()
    client.ensure_schema()
    sink = AnalyticsSink(client)
    pid = UUID(project_id)

    matches_by_mention: dict[str, list[BrandMatchResult]] = {}
    for row in matches or []:
        mid = str(row["mention_id"])
        matches_by_mention.setdefault(mid, []).append(
            BrandMatchResult(
                brand_id=UUID(str(row["brand_id"])),
                brand_name=str(row.get("brand_name") or ""),
                confidence=float(row["confidence"]),
                match_type=str(row["match_type"]),
                evidence=str(row.get("evidence") or ""),
                query_id=UUID(str(row["query_id"])) if row.get("query_id") else None,
            )
        )

    written = sink.sink_pipeline_result(
        mentions=normalized,
        matches_by_mention=matches_by_mention,
        project_id=pid,
    )
    return {"status": "ok", "stage": "analytics.aggregate", "written": written}
