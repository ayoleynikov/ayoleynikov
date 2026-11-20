"""ClickHouse schema + analytics sink tests (in-memory client)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pulse.clickhouse.client import InMemoryClickHouseClient
from pulse.clickhouse.schema import DDL_STATEMENTS, SCHEMA_COMMENTS
from pulse.clickhouse.sink import AnalyticsSink
from pulse.ingestion.normalize import normalize_mention
from pulse.matching.matcher import BrandMatchResult
from pulse.workers.analytics_tasks import sink_to_clickhouse


def test_schema_documents_dedup_and_tenant_isolation() -> None:
    assert "ReplacingMergeTree" in "\n".join(DDL_STATEMENTS)
    assert "SummingMergeTree" in "\n".join(DDL_STATEMENTS)
    assert "project_mentions" in "\n".join(DDL_STATEMENTS)
    assert "shared global" in SCHEMA_COMMENTS.lower() or "shared global" in SCHEMA_COMMENTS
    # Explicit: ORDER BY includes natural keys — uniqueness via merge, not insert.
    assert any("ORDER BY (source, external_id)" in ddl for ddl in DDL_STATEMENTS)
    assert any("ORDER BY (project_id, mention_id)" in ddl for ddl in DDL_STATEMENTS)


def test_sink_writes_catalog_and_project_tables() -> None:
    client = InMemoryClickHouseClient()
    client.ensure_schema()
    sink = AnalyticsSink(client)
    project_id = uuid4()
    mention = normalize_mention(
        {
            "source": "gdelt",
            "external_id": "https://example.com/a",
            "title": "Hello",
            "source_url": "https://example.com/a",
            "collected_at": datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        }
    )
    brand = uuid4()
    written = sink.sink_pipeline_result(
        mentions=[mention],
        matches_by_mention={
            mention.mention_id or "": [
                BrandMatchResult(
                    brand_id=brand,
                    brand_name="Acme",
                    confidence=0.9,
                    match_type="alias",
                    evidence="Acme",
                )
            ]
        },
        project_id=project_id,
    )
    assert written["mention_catalog"] == 1
    assert written["project_mentions"] == 1
    assert written["mention_matches"] == 1
    assert len(client.tables["mention_catalog"]) == 1
    # Shared catalog has no project_id column
    assert "project_id" not in client.tables["mention_catalog"][0]
    assert client.tables["project_mentions"][0]["project_id"] == project_id


def test_sink_task_requires_project_id() -> None:
    from pulse.workers.retry import PermanentTaskError
    import pytest

    with pytest.raises(PermanentTaskError):
        sink_to_clickhouse.run(mentions=[], project_id=None)


def test_sink_task_with_memory_client(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = InMemoryClickHouseClient()
    client.ensure_schema()
    monkeypatch.setattr(
        "pulse.workers.analytics_tasks.get_clickhouse_client",
        lambda: client,
    )
    project_id = str(uuid4())
    mention = normalize_mention(
        {
            "source": "gdelt",
            "external_id": "https://example.com/b",
            "title": "World",
            "collected_at": datetime(2024, 2, 1, tzinfo=UTC),
        }
    ).model_dump(mode="json")
    out = sink_to_clickhouse.run(mentions=[mention], matches=[], project_id=project_id)
    assert out["status"] == "ok"
    assert out["written"]["mention_catalog"] == 1
