"""Parse GDELT DOC 2.0 ArtList JSON into NormalizedMention objects."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pulse.connectors.types import (
    ConnectorError,
    ConnectorErrorKind,
    NormalizedMention,
    canonicalize_url,
)


def parse_artlist_response(
    payload: dict[str, Any] | list[Any],
    *,
    collected_at: datetime,
    source_version: str,
) -> list[NormalizedMention]:
    """Parse DOC 2.0 JSON. Raises on malformed payloads — never invents articles."""
    if isinstance(payload, list):
        articles = payload
    elif isinstance(payload, dict):
        if "error" in payload:
            raise ConnectorError(
                f"GDELT API error: {payload.get('error')}",
                kind=ConnectorErrorKind.PERMANENT,
                retryable=False,
                details=payload if isinstance(payload, dict) else {},
            )
        articles = payload.get("articles")
        if articles is None:
            # Some responses nest differently; require explicit articles key.
            raise ConnectorError(
                "GDELT response missing 'articles' array",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
                details={"keys": list(payload.keys())},
            )
    else:
        raise ConnectorError(
            "GDELT response must be object or list",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )

    if not isinstance(articles, list):
        raise ConnectorError(
            "GDELT 'articles' must be a list",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )

    mentions: list[NormalizedMention] = []
    for item in articles:
        if not isinstance(item, dict):
            raise ConnectorError(
                "GDELT article entry must be an object",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            )
        mentions.append(_article_to_mention(item, collected_at=collected_at, source_version=source_version))
    return mentions


def _article_to_mention(
    article: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
) -> NormalizedMention:
    url = article.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ConnectorError(
            "GDELT article missing url",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )
    url = url.strip()
    try:
        canonical = canonicalize_url(url)
    except ConnectorError:
        canonical = url

    title = article.get("title")
    title_s = str(title).strip() if title is not None else None
    seendate = article.get("seendate")
    published = _parse_seendate(seendate)

    # Prefer URL as external_id (stable across GDELT pulls); never invent IDs.
    external_id = url
    domain = article.get("domain")
    language = article.get("language")
    source_country = article.get("sourcecountry")

    metadata: dict[str, Any] = {}
    for key in ("domain", "language", "sourcecountry", "seendate", "socialimage"):
        if article.get(key) is not None:
            metadata[key] = article[key]

    mention = NormalizedMention(
        source="gdelt",
        external_id=external_id,
        source_url=url,
        author_id=str(domain) if domain else None,
        author_name=str(domain) if domain else None,
        content=None,  # DOC ArtList does not include full body — do not invent
        title=title_s,
        language=str(language) if language else None,
        published_at=published,
        collected_at=collected_at,
        engagement={},
        metadata=metadata,
        canonical_url=canonical,
        source_version=source_version,
    )
    return mention.ensure_hashes()


def _parse_seendate(value: Any) -> datetime | None:
    """GDELT seendate is typically YYYYMMDDTHHMMSSZ or similar."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
