"""Multi-level mention deduplication.

L1 source+external_id · L2 canonical URL · L3 content fingerprint · L4 cluster scaffold.
Mentions remain distinct from event clusters (L4 does not merge mention rows).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable

from pulse.connectors.types import NormalizedMention
from pulse.ingestion.normalize import content_fingerprint


class DedupLevel(StrEnum):
    L1_SOURCE_EXTERNAL_ID = "l1_source_external_id"
    L2_CANONICAL_URL = "l2_canonical_url"
    L3_CONTENT_FINGERPRINT = "l3_content_fingerprint"
    L4_EVENT_CLUSTER = "l4_event_cluster"  # scaffold only


@dataclass(frozen=True, slots=True)
class DedupHit:
    level: DedupLevel
    key: str
    existing_mention_id: str | None = None


@dataclass
class DedupDecision:
    is_duplicate: bool
    hits: list[DedupHit] = field(default_factory=list)
    primary_mention_id: str | None = None
    # L4 scaffold: optional cluster key suggestion (does not collapse mentions).
    suggested_cluster_key: str | None = None

    @property
    def highest_level(self) -> DedupLevel | None:
        if not self.hits:
            return None
        order = list(DedupLevel)
        return sorted(self.hits, key=lambda h: order.index(h.level))[0].level


@dataclass
class DedupIndex:
    """In-memory / batch index for L1–L3 keys."""

    by_source_external: dict[tuple[str, str], str] = field(default_factory=dict)
    by_canonical_url: dict[str, str] = field(default_factory=dict)
    by_content_hash: dict[str, str] = field(default_factory=dict)

    def observe(self, mention: NormalizedMention) -> None:
        mid = mention.mention_id or f"{mention.source}:{mention.external_id}"
        self.by_source_external[(mention.source, mention.external_id)] = mid
        if mention.canonical_url:
            self.by_canonical_url.setdefault(mention.canonical_url, mid)
        fp = mention.content_hash or content_fingerprint(mention.title, mention.content)
        if fp:
            self.by_content_hash.setdefault(fp, mid)

    def extend(self, mentions: Iterable[NormalizedMention]) -> None:
        for mention in mentions:
            self.observe(mention)


def evaluate_dedup(
    mention: NormalizedMention,
    index: DedupIndex,
    *,
    enable_l4_scaffold: bool = True,
) -> DedupDecision:
    """Return duplicate hits against an index. Never silently drops — caller decides."""
    hits: list[DedupHit] = []

    l1_key = (mention.source, mention.external_id)
    if l1_key in index.by_source_external:
        hits.append(
            DedupHit(
                level=DedupLevel.L1_SOURCE_EXTERNAL_ID,
                key=f"{mention.source}:{mention.external_id}",
                existing_mention_id=index.by_source_external[l1_key],
            )
        )

    if mention.canonical_url and mention.canonical_url in index.by_canonical_url:
        existing = index.by_canonical_url[mention.canonical_url]
        # L2 only if it's not the same L1 identity we already own.
        if existing != (mention.mention_id or ""):
            hits.append(
                DedupHit(
                    level=DedupLevel.L2_CANONICAL_URL,
                    key=mention.canonical_url,
                    existing_mention_id=existing,
                )
            )

    fp = mention.content_hash or content_fingerprint(mention.title, mention.content)
    if fp and fp in index.by_content_hash:
        existing = index.by_content_hash[fp]
        if existing != (mention.mention_id or ""):
            hits.append(
                DedupHit(
                    level=DedupLevel.L3_CONTENT_FINGERPRINT,
                    key=fp,
                    existing_mention_id=existing,
                )
            )

    suggested_cluster = None
    if enable_l4_scaffold and fp:
        # Scaffold only: cluster key suggestion for later semantic grouping.
        # Mentions stay separate rows — clusters are a different entity.
        suggested_cluster = f"cluster:fp:{fp[:16]}"

    primary = hits[0].existing_mention_id if hits else mention.mention_id
    return DedupDecision(
        is_duplicate=bool(hits),
        hits=hits,
        primary_mention_id=primary,
        suggested_cluster_key=suggested_cluster,
    )


def dedupe_batch(
    mentions: list[NormalizedMention],
    *,
    existing: DedupIndex | None = None,
) -> tuple[list[NormalizedMention], list[tuple[NormalizedMention, DedupDecision]]]:
    """Dedupe within a batch (+ optional existing index).

    Returns (unique_mentions, duplicates_with_decisions).
    """
    index = existing or DedupIndex()
    unique: list[NormalizedMention] = []
    duplicates: list[tuple[NormalizedMention, DedupDecision]] = []

    for mention in mentions:
        decision = evaluate_dedup(mention, index)
        if decision.is_duplicate:
            duplicates.append((mention, decision))
        else:
            unique.append(mention)
            index.observe(mention)
    return unique, duplicates
