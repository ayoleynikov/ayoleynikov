"""ClickHouse DDL with explicit dedup design.

Design notes (do NOT assume MergeTree uniqueness):
- Append-only inserts; duplicates may exist until merges.
- ``mention_catalog`` / ``mention_matches`` use ReplacingMergeTree(version) keyed by
  natural identity; readers should use FINAL or argMax for exact uniqueness.
- ``project_mentions`` isolates tenants: (project_id, mention_id) — shared catalog
  holds global mention bodies once; projects link via project_mentions.
- ``hourly_metrics`` uses SummingMergeTree for additive counters.
"""

from __future__ import annotations

SCHEMA_COMMENTS = """
Tenant isolation:
  - mention_catalog: shared global mention bodies (no project_id)
  - project_mentions: per-tenant association + project-scoped metadata
  - mention_matches / mention_analytics / event_clusters / hourly_metrics: project_id required
"""

DDL_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS mention_catalog
    (
        mention_id String,
        source LowCardinality(String),
        external_id String,
        source_url String,
        author_id String,
        author_name String,
        content String,
        title String,
        language LowCardinality(String),
        published_at DateTime64(3, 'UTC'),
        collected_at DateTime64(3, 'UTC'),
        content_hash String,
        canonical_url String,
        source_version LowCardinality(String),
        version UInt64,
        inserted_at DateTime64(3, 'UTC') DEFAULT now64(3)
    )
    ENGINE = ReplacingMergeTree(version)
    ORDER BY (source, external_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS project_mentions
    (
        project_id UUID,
        mention_id String,
        source LowCardinality(String),
        collected_at DateTime64(3, 'UTC'),
        version UInt64,
        inserted_at DateTime64(3, 'UTC') DEFAULT now64(3)
    )
    ENGINE = ReplacingMergeTree(version)
    ORDER BY (project_id, mention_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS mention_matches
    (
        project_id UUID,
        mention_id String,
        brand_id UUID,
        query_id Nullable(UUID),
        confidence Float64,
        match_type LowCardinality(String),
        evidence String,
        version UInt64,
        matched_at DateTime64(3, 'UTC') DEFAULT now64(3)
    )
    ENGINE = ReplacingMergeTree(version)
    ORDER BY (project_id, mention_id, brand_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS mention_analytics
    (
        project_id UUID,
        mention_id String,
        source LowCardinality(String),
        language LowCardinality(String),
        published_at DateTime64(3, 'UTC'),
        sentiment_stub Float64 DEFAULT 0,
        version UInt64,
        inserted_at DateTime64(3, 'UTC') DEFAULT now64(3)
    )
    ENGINE = ReplacingMergeTree(version)
    ORDER BY (project_id, mention_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS event_clusters
    (
        project_id UUID,
        cluster_key String,
        label String,
        status LowCardinality(String),
        mention_count UInt64,
        version UInt64,
        updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
    )
    ENGINE = ReplacingMergeTree(version)
    ORDER BY (project_id, cluster_key)
    """,
    """
    CREATE TABLE IF NOT EXISTS hourly_metrics
    (
        project_id UUID,
        hour DateTime('UTC'),
        source LowCardinality(String),
        mentions UInt64,
        matches UInt64
    )
    ENGINE = SummingMergeTree((mentions, matches))
    ORDER BY (project_id, hour, source)
    """,
]


def ensure_database_sql(database: str) -> str:
    # Identifier only — caller must pass a safe db name from settings.
    return f"CREATE DATABASE IF NOT EXISTS {database}"
