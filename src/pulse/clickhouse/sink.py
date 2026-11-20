"""Sink matched / normalized mentions into ClickHouse analytics tables."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Sequence
from uuid import UUID

from pulse.clickhouse.client import ClickHouseClient
from pulse.connectors.types import NormalizedMention
from pulse.logging import get_logger
from pulse.matching.matcher import BrandMatchResult

logger = get_logger(__name__)


def _version() -> int:
    return int(time.time() * 1000)


def _dt(value: datetime | None) -> datetime:
    if value is None:
        return datetime(1970, 1, 1, tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AnalyticsSink:
    """Write shared catalog + tenant-scoped analytics after matching.

    Dedup contract: rows are append-only with monotonically increasing ``version``.
    ClickHouse ReplacingMergeTree collapses duplicates asynchronously; readers
    must use FINAL / argMax for exact uniqueness. Never assume insert uniqueness.
    """

    def __init__(self, client: ClickHouseClient) -> None:
        self.client = client

    def sink_mentions(
        self,
        mentions: Sequence[NormalizedMention],
        *,
        project_id: UUID | None = None,
    ) -> dict[str, int]:
        version = _version()
        catalog_rows = []
        project_rows = []
        analytics_rows = []
        hourly: dict[tuple[str, str, str], dict[str, int]] = {}

        for mention in mentions:
            mid = mention.mention_id or ""
            catalog_rows.append(
                {
                    "mention_id": mid,
                    "source": mention.source,
                    "external_id": mention.external_id,
                    "source_url": mention.source_url or "",
                    "author_id": mention.author_id or "",
                    "author_name": mention.author_name or "",
                    "content": mention.content or "",
                    "title": mention.title or "",
                    "language": mention.language or "",
                    "published_at": _dt(mention.published_at),
                    "collected_at": _dt(mention.collected_at),
                    "content_hash": mention.content_hash or "",
                    "canonical_url": mention.canonical_url or "",
                    "source_version": mention.source_version,
                    "version": version,
                }
            )
            if project_id is not None:
                project_rows.append(
                    {
                        "project_id": project_id,
                        "mention_id": mid,
                        "source": mention.source,
                        "collected_at": _dt(mention.collected_at),
                        "version": version,
                    }
                )
                analytics_rows.append(
                    {
                        "project_id": project_id,
                        "mention_id": mid,
                        "source": mention.source,
                        "language": mention.language or "",
                        "published_at": _dt(mention.published_at),
                        "sentiment_stub": 0.0,
                        "version": version,
                    }
                )
                hour = _dt(mention.collected_at).replace(minute=0, second=0, microsecond=0)
                key = (str(project_id), hour.isoformat(), mention.source)
                bucket = hourly.setdefault(key, {"mentions": 0, "matches": 0})
                bucket["mentions"] += 1

        written = {
            "mention_catalog": self.client.insert(
                "mention_catalog",
                catalog_rows,
                [
                    "mention_id",
                    "source",
                    "external_id",
                    "source_url",
                    "author_id",
                    "author_name",
                    "content",
                    "title",
                    "language",
                    "published_at",
                    "collected_at",
                    "content_hash",
                    "canonical_url",
                    "source_version",
                    "version",
                ],
            ),
            "project_mentions": 0,
            "mention_analytics": 0,
            "hourly_metrics": 0,
        }
        if project_rows:
            written["project_mentions"] = self.client.insert(
                "project_mentions",
                project_rows,
                ["project_id", "mention_id", "source", "collected_at", "version"],
            )
            written["mention_analytics"] = self.client.insert(
                "mention_analytics",
                analytics_rows,
                [
                    "project_id",
                    "mention_id",
                    "source",
                    "language",
                    "published_at",
                    "sentiment_stub",
                    "version",
                ],
            )
            metric_rows = [
                {
                    "project_id": UUID(pid),
                    "hour": datetime.fromisoformat(hour),
                    "source": source,
                    "mentions": counts["mentions"],
                    "matches": counts["matches"],
                }
                for (pid, hour, source), counts in hourly.items()
            ]
            written["hourly_metrics"] = self.client.insert(
                "hourly_metrics",
                metric_rows,
                ["project_id", "hour", "source", "mentions", "matches"],
            )

        logger.info("clickhouse_mentions_sunk", extra=written)
        return written

    def sink_matches(
        self,
        matches: Sequence[BrandMatchResult],
        *,
        project_id: UUID,
        mention_id: str,
    ) -> int:
        if not matches:
            return 0
        version = _version()
        rows = [
            {
                "project_id": project_id,
                "mention_id": mention_id,
                "brand_id": m.brand_id,
                "query_id": m.query_id,
                "confidence": m.confidence,
                "match_type": m.match_type,
                "evidence": m.evidence or "",
                "version": version,
            }
            for m in matches
        ]
        count = self.client.insert(
            "mention_matches",
            rows,
            [
                "project_id",
                "mention_id",
                "brand_id",
                "query_id",
                "confidence",
                "match_type",
                "evidence",
                "version",
            ],
        )
        # Bump hourly match counters (append-only; SummingMergeTree aggregates).
        hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        self.client.insert(
            "hourly_metrics",
            [
                {
                    "project_id": project_id,
                    "hour": hour,
                    "source": "matched",
                    "mentions": 0,
                    "matches": count,
                }
            ],
            ["project_id", "hour", "source", "mentions", "matches"],
        )
        return count

    def sink_pipeline_result(
        self,
        *,
        mentions: Sequence[NormalizedMention],
        matches_by_mention: dict[str, Sequence[BrandMatchResult]],
        project_id: UUID,
    ) -> dict[str, int]:
        """Sink after normalize/dedupe/match — catalog + tenant rows + matches."""
        written = self.sink_mentions(mentions, project_id=project_id)
        match_count = 0
        for mention in mentions:
            mid = mention.mention_id or ""
            match_count += self.sink_matches(
                matches_by_mention.get(mid, ()),
                project_id=project_id,
                mention_id=mid,
            )
        written["mention_matches"] = match_count
        return written
