"""Ingestion pipeline: validate → normalize → dedupe → brand match (classify stub)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence
from uuid import UUID

from pulse.connectors.types import NormalizedMention
from pulse.ingestion.dedupe import DedupDecision, DedupIndex, evaluate_dedup
from pulse.ingestion.normalize import NormalizationError, normalize_mention
from pulse.matching.matcher import (
    BrandAliasView,
    BrandMatchResult,
    MonitoringQueryView,
    match_mention_against_brands,
)


@dataclass
class PipelineItemResult:
    raw: dict[str, Any]
    mention: NormalizedMention | None = None
    error: str | None = None
    dedupe: DedupDecision | None = None
    matches: list[BrandMatchResult] = field(default_factory=list)
    classification: dict[str, Any] = field(default_factory=lambda: {"status": "not_implemented", "phase": "phase-5"})


@dataclass
class PipelineResult:
    accepted: list[PipelineItemResult] = field(default_factory=list)
    duplicates: list[PipelineItemResult] = field(default_factory=list)
    rejected: list[PipelineItemResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "accepted": len(self.accepted),
            "duplicates": len(self.duplicates),
            "rejected": len(self.rejected),
            "matches": sum(len(i.matches) for i in self.accepted),
        }


def run_ingestion_pipeline(
    raw_items: Sequence[dict[str, Any]],
    *,
    existing_index: DedupIndex | None = None,
    aliases: Sequence[BrandAliasView] = (),
    queries: Sequence[MonitoringQueryView] = (),
    brand_names: dict[UUID, str] | None = None,
    project_id: UUID | None = None,
) -> PipelineResult:
    """Run normalize → dedupe → brand match. Never silently drops failures."""
    result = PipelineResult()
    normalized: list[tuple[dict[str, Any], NormalizedMention]] = []

    for raw in raw_items:
        try:
            mention = normalize_mention(raw)
            normalized.append((raw, mention))
        except (NormalizationError, Exception) as exc:  # noqa: BLE001 — surface as rejected
            result.rejected.append(PipelineItemResult(raw=raw, error=str(exc)))

    index = existing_index or DedupIndex()
    for raw, mention in normalized:
        decision = evaluate_dedup(mention, index)
        if decision.is_duplicate:
            result.duplicates.append(
                PipelineItemResult(raw=raw, mention=mention, dedupe=decision)
            )
            continue
        matches = match_mention_against_brands(
            mention,
            aliases=aliases,
            queries=queries,
            brand_names=brand_names,
        )
        result.accepted.append(
            PipelineItemResult(
                raw=raw,
                mention=mention,
                dedupe=DedupDecision(is_duplicate=False, primary_mention_id=mention.mention_id),
                matches=matches,
            )
        )
        index.observe(mention)

    _ = project_id  # reserved for tenant-scoped persistence in store layer
    return result
