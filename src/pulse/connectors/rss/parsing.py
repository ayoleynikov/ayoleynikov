"""RSS/Atom entry parsing into NormalizedMention."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from time import struct_time

import feedparser

from pulse.connectors.types import (
    ConnectorError,
    ConnectorErrorKind,
    NormalizedMention,
    canonicalize_url,
)


def _struct_time_to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


def _parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_feed(
    body: bytes | str,
    *,
    feed_url: str,
    collected_at: datetime,
    source_version: str,
    max_entries: int,
) -> tuple[list[NormalizedMention], dict[str, Any]]:
    """Parse RSS/Atom body into normalized mentions.

    Raises ``ConnectorError`` on empty/unparseable feeds — never returns a silent empty success
    when the document is invalid.
    """
    parsed = feedparser.parse(body)
    bozo = bool(getattr(parsed, "bozo", False))
    entries = list(getattr(parsed, "entries", []) or [])
    feed_meta = getattr(parsed, "feed", {}) or {}

    # feedparser sets bozo for many recoverable quirks; only fail hard when there is
    # no usable feed structure and no entries.
    has_feed_identity = bool(feed_meta.get("title") or feed_meta.get("link") or feed_meta.get("id"))
    if not entries and not has_feed_identity:
        detail = ""
        if bozo and getattr(parsed, "bozo_exception", None) is not None:
            detail = str(parsed.bozo_exception)
        msg = f"unparseable or empty feed at {feed_url}: {detail or 'no entries or feed metadata'}"
        raise ConnectorError(msg, kind=ConnectorErrorKind.PARSE, retryable=False)

    mentions: list[NormalizedMention] = []
    for entry in entries[:max_entries]:
        mention = entry_to_mention(
            entry,
            feed_url=feed_url,
            collected_at=collected_at,
            source_version=source_version,
        )
        mentions.append(mention)

    meta = {
        "feed_title": feed_meta.get("title"),
        "feed_link": feed_meta.get("link"),
        "bozo": bozo,
        "entry_count": len(entries),
        "returned_count": len(mentions),
    }
    return mentions, meta


def entry_to_mention(
    entry: dict[str, Any],
    *,
    feed_url: str,
    collected_at: datetime,
    source_version: str,
) -> NormalizedMention:
    """Convert one feedparser entry into a NormalizedMention."""
    external_id = _entry_external_id(entry)
    link = _entry_link(entry)
    canonical: str | None = None
    if link:
        try:
            canonical = canonicalize_url(link)
        except ConnectorError:
            canonical = link

    title = _as_text(entry.get("title"))
    content = _entry_content(entry)
    author = _as_text(entry.get("author"))
    published = _struct_time_to_datetime(entry.get("published_parsed")) or _struct_time_to_datetime(
        entry.get("updated_parsed")
    )

    language = None
    if entry.get("content") and isinstance(entry["content"], list) and entry["content"]:
        language = entry["content"][0].get("language")

    mention = NormalizedMention(
        source="rss",
        external_id=external_id,
        source_url=link or feed_url,
        author_id=None,
        author_name=author,
        content=content,
        title=title,
        language=language,
        published_at=published,
        collected_at=collected_at,
        engagement={},
        metadata={
            "feed_url": feed_url,
            "guid": entry.get("id") or entry.get("guid"),
            "tags": [t.get("term") for t in entry.get("tags", []) if isinstance(t, dict)],
        },
        canonical_url=canonical,
        source_version=source_version,
    )
    return mention.ensure_hashes()


def _entry_external_id(entry: dict[str, Any]) -> str:
    for key in ("id", "guid", "link"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if hasattr(value, "strip") and str(value).strip():
            return str(value).strip()
    # Last resort: hash of title+published — still an identity, not invented metadata fields.
    title = _as_text(entry.get("title")) or ""
    published = entry.get("published") or entry.get("updated") or ""
    if not title and not published:
        msg = "feed entry missing id/guid/link/title"
        raise ConnectorError(msg, kind=ConnectorErrorKind.PARSE, retryable=False)
    return f"rss-fallback:{title}|{published}"


def _entry_link(entry: dict[str, Any]) -> str | None:
    link = entry.get("link")
    if isinstance(link, str) and link.strip():
        return link.strip()
    links = entry.get("links") or []
    for item in links:
        if isinstance(item, dict) and item.get("rel") in {None, "alternate"} and item.get("href"):
            return str(item["href"]).strip()
    return None


def _entry_content(entry: dict[str, Any]) -> str | None:
    if entry.get("summary"):
        return _as_text(entry.get("summary"))
    content = entry.get("content")
    if isinstance(content, list) and content:
        return _as_text(content[0].get("value"))
    return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["parse_feed", "entry_to_mention", "_parse_http_date"]
