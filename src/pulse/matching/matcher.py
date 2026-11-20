"""Alias-aware brand matching with confidence scores.

Matching runs in-process against mention text. Monitoring query AST is evaluated
in memory — user syntax is never injected into SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from pulse.connectors.types import NormalizedMention
from pulse.ingestion.normalize import fold_text
from pulse.matching.ast import BooleanQuery, evaluate_ast, parse_boolean_query


@dataclass(frozen=True, slots=True)
class BrandAliasView:
    brand_id: UUID
    brand_name: str
    alias: str
    is_primary: bool = False


@dataclass(frozen=True, slots=True)
class MonitoringQueryView:
    query_id: UUID
    project_id: UUID
    brand_id: UUID | None
    query_text: str
    ast: BooleanQuery | None = None


@dataclass(frozen=True, slots=True)
class BrandMatchResult:
    brand_id: UUID
    brand_name: str
    confidence: float
    match_type: str  # exact | phrase | alias | boolean_query
    evidence: str
    query_id: UUID | None = None


def _haystack(mention: NormalizedMention) -> str:
    parts = [p for p in (mention.title, mention.content, mention.author_name) if p]
    return fold_text(" ".join(parts))


def _alias_confidence(alias: str, *, is_primary: bool, matched_as_phrase: bool) -> float:
    base = 0.92 if is_primary else 0.85
    if matched_as_phrase or " " in alias.strip():
        return min(0.99, base + 0.05)
    # Short tokens are weaker signals.
    if len(alias.strip()) <= 3:
        return max(0.55, base - 0.25)
    return base


def match_aliases(
    mention: NormalizedMention,
    aliases: Sequence[BrandAliasView],
) -> list[BrandMatchResult]:
    text = _haystack(mention)
    if not text:
        return []
    results: list[BrandMatchResult] = []
    seen_brands: set[UUID] = set()
    # Longer aliases first for phrase preference.
    ordered = sorted(aliases, key=lambda a: len(a.alias), reverse=True)
    for alias in ordered:
        needle = fold_text(alias.alias)
        if not needle or needle not in text:
            continue
        if alias.brand_id in seen_brands:
            continue
        phrase = " " in needle
        match_type = "phrase" if phrase else ("exact" if alias.is_primary else "alias")
        results.append(
            BrandMatchResult(
                brand_id=alias.brand_id,
                brand_name=alias.brand_name,
                confidence=_alias_confidence(alias.alias, is_primary=alias.is_primary, matched_as_phrase=phrase),
                match_type=match_type,
                evidence=alias.alias,
            )
        )
        seen_brands.add(alias.brand_id)
    return results


def match_boolean_queries(
    mention: NormalizedMention,
    queries: Sequence[MonitoringQueryView],
    *,
    brand_names: dict[UUID, str] | None = None,
) -> list[BrandMatchResult]:
    text = _haystack(mention)
    if not text:
        return []
    names = brand_names or {}
    results: list[BrandMatchResult] = []
    for query in queries:
        ast = query.ast or parse_boolean_query(query.query_text)
        if not evaluate_ast(ast.root, text):
            continue
        brand_id = query.brand_id
        if brand_id is None:
            continue
        results.append(
            BrandMatchResult(
                brand_id=brand_id,
                brand_name=names.get(brand_id, str(brand_id)),
                confidence=0.8,
                match_type="boolean_query",
                evidence=query.query_text,
                query_id=query.query_id,
            )
        )
    return results


def match_mention_against_brands(
    mention: NormalizedMention,
    *,
    aliases: Sequence[BrandAliasView],
    queries: Sequence[MonitoringQueryView] = (),
    brand_names: dict[UUID, str] | None = None,
) -> list[BrandMatchResult]:
    """Multi-brand match: aliases first, then Boolean monitoring queries."""
    by_brand: dict[UUID, BrandMatchResult] = {}
    for hit in match_aliases(mention, aliases):
        prev = by_brand.get(hit.brand_id)
        if prev is None or hit.confidence > prev.confidence:
            by_brand[hit.brand_id] = hit
    for hit in match_boolean_queries(mention, queries, brand_names=brand_names):
        prev = by_brand.get(hit.brand_id)
        if prev is None or hit.confidence > prev.confidence:
            by_brand[hit.brand_id] = hit
    return sorted(by_brand.values(), key=lambda m: m.confidence, reverse=True)
