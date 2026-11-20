"""Validate and normalize raw mention payloads into universal Mention fields.

Never invent metadata — only preserve what the source provided (plus deterministic hashes).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from pulse.connectors.types import ConnectorError, ConnectorErrorKind, NormalizedMention, canonicalize_url


class NormalizationError(ValueError):
    """Invalid mention payload — must not be silently discarded upstream."""


class RawMentionInput(BaseModel):
    """Loose input accepted before normalization (connector or API payload)."""

    source: str
    external_id: str
    source_url: str | None = None
    author_id: str | None = None
    author_name: str | None = None
    content: str | None = None
    title: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    collected_at: datetime | None = None
    engagement: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    canonical_url: str | None = None
    source_version: str = "1"

    @field_validator("source", "external_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "source and external_id are required"
            raise ValueError(msg)
        return cleaned


_WHITESPACE_RE = re.compile(r"\s+")


def fold_text(value: str) -> str:
    """Unicode NFKC + casefold + collapse whitespace for fingerprinting / matching."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.casefold()
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def content_fingerprint(title: str | None, content: str | None) -> str | None:
    """L3 fingerprint from title+content only (no source identity)."""
    parts = [p for p in (title, content) if p]
    if not parts:
        return None
    folded = fold_text(" ".join(parts))
    if not folded:
        return None
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def mention_identity(source: str, external_id: str) -> str:
    return hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest()


def validate_raw(payload: dict[str, Any] | RawMentionInput | NormalizedMention) -> RawMentionInput:
    """Validate required fields; raise NormalizationError on failure (never silent)."""
    try:
        if isinstance(payload, NormalizedMention):
            return RawMentionInput.model_validate(payload.model_dump())
        if isinstance(payload, RawMentionInput):
            return payload
        return RawMentionInput.model_validate(payload)
    except ValidationError as exc:
        raise NormalizationError(str(exc)) from exc


def normalize_mention(
    payload: dict[str, Any] | RawMentionInput | NormalizedMention,
    *,
    collected_at: datetime | None = None,
) -> NormalizedMention:
    """Produce a NormalizedMention with UTC timestamps and deterministic hashes."""
    raw = validate_raw(payload)
    now = collected_at or datetime.now(UTC)
    collected = raw.collected_at or now
    if collected.tzinfo is None:
        raise NormalizationError("collected_at must be timezone-aware UTC")
    collected = collected.astimezone(UTC)

    published = raw.published_at
    if published is not None:
        if published.tzinfo is None:
            raise NormalizationError("published_at must be timezone-aware UTC")
        published = published.astimezone(UTC)

    canonical = raw.canonical_url
    if not canonical and raw.source_url:
        try:
            canonical = canonicalize_url(raw.source_url)
        except ConnectorError:
            canonical = raw.source_url

    # Strip None-valued metadata keys; do not add invented keys.
    metadata = {k: v for k, v in (raw.metadata or {}).items() if v is not None}
    engagement = {k: v for k, v in (raw.engagement or {}).items() if v is not None}

    mention = NormalizedMention(
        mention_id=mention_identity(raw.source, raw.external_id),
        source=raw.source,
        external_id=raw.external_id,
        source_url=raw.source_url,
        author_id=raw.author_id,
        author_name=raw.author_name,
        content=raw.content,
        title=raw.title,
        language=raw.language,
        published_at=published,
        collected_at=collected,
        engagement=engagement,
        metadata=metadata,
        content_hash=content_fingerprint(raw.title, raw.content),
        canonical_url=canonical,
        source_version=raw.source_version or "1",
    )
    return mention
