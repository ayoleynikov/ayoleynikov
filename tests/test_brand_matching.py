"""Brand alias + Boolean matching tests (tenant-safe, in-process)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pulse.ingestion.normalize import normalize_mention
from pulse.ingestion.pipeline import run_ingestion_pipeline
from pulse.matching.ast import parse_boolean_query
from pulse.matching.matcher import (
    BrandAliasView,
    MonitoringQueryView,
    match_mention_against_brands,
)
from pulse.workers.ingestion_tasks import match_brands_task, normalize_batch


def _mention(text: str, *, external_id: str = "1"):
    return normalize_mention(
        {
            "source": "rss",
            "external_id": external_id,
            "content": text,
            "collected_at": datetime(2024, 1, 1, tzinfo=UTC),
        }
    )


def test_multi_brand_alias_matching() -> None:
    acme = uuid4()
    beta = uuid4()
    aliases = [
        BrandAliasView(brand_id=acme, brand_name="Acme", alias="Acme", is_primary=True),
        BrandAliasView(brand_id=acme, brand_name="Acme", alias="Acme Inc"),
        BrandAliasView(brand_id=beta, brand_name="Beta", alias="BetaCo", is_primary=True),
    ]
    mention = _mention("Talking about Acme Inc and BetaCo today")
    matches = match_mention_against_brands(mention, aliases=aliases)
    brand_ids = {m.brand_id for m in matches}
    assert acme in brand_ids and beta in brand_ids
    assert all(0.0 < m.confidence <= 1.0 for m in matches)


def test_boolean_query_match() -> None:
    brand = uuid4()
    qid = uuid4()
    project = uuid4()
    queries = [
        MonitoringQueryView(
            query_id=qid,
            project_id=project,
            brand_id=brand,
            query_text='"Acme Corp" AND launch',
            ast=parse_boolean_query('"Acme Corp" AND launch'),
        )
    ]
    hit = _mention("Acme Corp announces launch")
    miss = _mention("Acme Corp announces layoff")
    assert match_mention_against_brands(hit, aliases=[], queries=queries)
    assert not match_mention_against_brands(miss, aliases=[], queries=queries)


def test_pipeline_normalize_dedupe_match() -> None:
    brand = uuid4()
    aliases = [BrandAliasView(brand_id=brand, brand_name="Acme", alias="Acme", is_primary=True)]
    items = [
        {
            "source": "rss",
            "external_id": "1",
            "content": "Acme rocks",
            "collected_at": "2024-01-01T00:00:00+00:00",
        },
        {
            "source": "rss",
            "external_id": "1",
            "content": "Acme rocks again",
            "collected_at": "2024-01-01T00:00:00+00:00",
        },
    ]
    result = run_ingestion_pipeline(items, aliases=aliases)
    assert result.summary()["accepted"] == 1
    assert result.summary()["duplicates"] == 1
    assert result.accepted[0].matches
    assert result.accepted[0].matches[0].brand_id == brand


def test_celery_normalize_and_match_tasks() -> None:
    out = normalize_batch.run(
        items=[
            {
                "source": "rss",
                "external_id": "z",
                "content": "hello",
                "collected_at": "2024-01-01T00:00:00+00:00",
            }
        ]
    )
    assert out["status"] == "ok"
    assert out["accepted"] == 1

    brand = uuid4()
    match_out = match_brands_task.run(
        mention=out["mentions"][0],
        aliases=[{"brand_id": str(brand), "brand_name": "HelloCo", "alias": "hello", "is_primary": True}],
    )
    assert match_out["match_count"] >= 1
