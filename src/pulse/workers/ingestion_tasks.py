"""Celery tasks for normalize / dedupe / brand matching (Phase 5 — real logic)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pulse.ingestion.dedupe import DedupIndex, dedupe_batch
from pulse.ingestion.normalize import NormalizationError, normalize_mention
from pulse.ingestion.pipeline import run_ingestion_pipeline
from pulse.matching.ast import QueryParseError, parse_boolean_query
from pulse.matching.matcher import BrandAliasView, MonitoringQueryView, match_mention_against_brands
from pulse.workers.base_task import PulseTask
from pulse.workers.celery_app import celery_app
from pulse.workers.retry import PermanentTaskError


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.ingestion_tasks.normalize_batch",
)
def normalize_batch(self: PulseTask, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize a batch of raw mention payloads."""
    items = items or []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in items:
        try:
            mention = normalize_mention(raw)
            accepted.append(mention.model_dump(mode="json"))
        except NormalizationError as exc:
            rejected.append({"raw": raw, "error": str(exc)})
    return {
        "status": "ok",
        "stage": "ingestion.normalize",
        "accepted": len(accepted),
        "rejected": len(rejected),
        "mentions": accepted,
        "errors": rejected,
    }


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.ingestion_tasks.dedupe_batch",
)
def dedupe_batch_task(
    self: PulseTask,
    mentions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dedupe normalized mentions (L1–L3); L4 cluster key scaffold included."""
    mentions = mentions or []
    normalized = []
    for payload in mentions:
        try:
            normalized.append(normalize_mention(payload))
        except NormalizationError as exc:
            raise PermanentTaskError(f"invalid mention in dedupe batch: {exc}") from exc

    unique, duplicates = dedupe_batch(normalized, existing=DedupIndex())
    return {
        "status": "ok",
        "stage": "ingestion.dedupe",
        "unique": len(unique),
        "duplicates": len(duplicates),
        "unique_mention_ids": [m.mention_id for m in unique],
        "duplicate_details": [
            {
                "mention_id": m.mention_id,
                "levels": [h.level.value for h in decision.hits],
                "primary_mention_id": decision.primary_mention_id,
                "suggested_cluster_key": decision.suggested_cluster_key,
            }
            for m, decision in duplicates
        ],
    }


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.ingestion_tasks.match_brands",
)
def match_brands_task(
    self: PulseTask,
    mention: dict[str, Any] | None = None,
    aliases: list[dict[str, Any]] | None = None,
    queries: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Match one mention against brand aliases + Boolean monitoring queries."""
    if not mention:
        raise PermanentTaskError("mention payload required")
    try:
        normalized = normalize_mention(mention)
    except NormalizationError as exc:
        raise PermanentTaskError(str(exc)) from exc

    alias_views: list[BrandAliasView] = []
    for row in aliases or []:
        alias_views.append(
            BrandAliasView(
                brand_id=UUID(str(row["brand_id"])),
                brand_name=str(row.get("brand_name") or row.get("alias")),
                alias=str(row["alias"]),
                is_primary=bool(row.get("is_primary", False)),
            )
        )

    query_views: list[MonitoringQueryView] = []
    brand_names: dict[UUID, str] = {}
    for row in queries or []:
        qtext = str(row["query_text"])
        try:
            ast = parse_boolean_query(qtext)
        except QueryParseError as exc:
            raise PermanentTaskError(f"invalid monitoring query: {exc}") from exc
        brand_id = UUID(str(row["brand_id"])) if row.get("brand_id") else None
        qid = UUID(str(row["query_id"])) if row.get("query_id") else UUID(int=0)
        project = UUID(str(row.get("project_id") or project_id or UUID(int=0)))
        query_views.append(
            MonitoringQueryView(
                query_id=qid,
                project_id=project,
                brand_id=brand_id,
                query_text=qtext,
                ast=ast,
            )
        )
        if brand_id and row.get("brand_name"):
            brand_names[brand_id] = str(row["brand_name"])

    matches = match_mention_against_brands(
        normalized,
        aliases=alias_views,
        queries=query_views,
        brand_names=brand_names,
    )
    return {
        "status": "ok",
        "stage": "matching.brand",
        "project_id": project_id,
        "mention_id": normalized.mention_id,
        "match_count": len(matches),
        "matches": [
            {
                "brand_id": str(m.brand_id),
                "brand_name": m.brand_name,
                "confidence": m.confidence,
                "match_type": m.match_type,
                "evidence": m.evidence,
                "query_id": str(m.query_id) if m.query_id else None,
            }
            for m in matches
        ],
    }


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.ingestion_tasks.run_pipeline",
)
def run_pipeline_task(
    self: PulseTask,
    items: list[dict[str, Any]] | None = None,
    aliases: list[dict[str, Any]] | None = None,
    queries: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Full in-process pipeline for a batch (normalize → dedupe → match)."""
    alias_views = [
        BrandAliasView(
            brand_id=UUID(str(a["brand_id"])),
            brand_name=str(a.get("brand_name") or a["alias"]),
            alias=str(a["alias"]),
            is_primary=bool(a.get("is_primary", False)),
        )
        for a in (aliases or [])
    ]
    query_views: list[MonitoringQueryView] = []
    for row in queries or []:
        ast = parse_boolean_query(str(row["query_text"]))
        query_views.append(
            MonitoringQueryView(
                query_id=UUID(str(row.get("query_id") or UUID(int=0))),
                project_id=UUID(str(row.get("project_id") or project_id or UUID(int=0))),
                brand_id=UUID(str(row["brand_id"])) if row.get("brand_id") else None,
                query_text=str(row["query_text"]),
                ast=ast,
            )
        )

    result = run_ingestion_pipeline(
        items or [],
        aliases=alias_views,
        queries=query_views,
        project_id=UUID(project_id) if project_id else None,
    )
    return {"status": "ok", "stage": "ingestion.pipeline", **result.summary()}
