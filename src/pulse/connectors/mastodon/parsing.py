"""Parse Mastodon status JSON into NormalizedMention objects."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pulse.connectors.types import (
    ConnectorError,
    ConnectorErrorKind,
    NormalizedMention,
    canonicalize_url,
)

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str | None:
    if text is None:
        return None
    return _TAG_RE.sub("", text).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def parse_status(
    status: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
    instance_host: str,
) -> NormalizedMention:
    """Map one Mastodon status. Raises on missing id — never invents posts."""
    if not isinstance(status, dict):
        raise ConnectorError(
            "Mastodon status must be an object",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )
    status_id = status.get("id")
    if status_id is None or str(status_id).strip() == "":
        raise ConnectorError(
            "Mastodon status missing id",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )
    external_id = f"{instance_host}:{status_id}"
    url = status.get("url") or status.get("uri")
    canonical = None
    if isinstance(url, str) and url.strip():
        try:
            canonical = canonicalize_url(url.strip())
        except ConnectorError:
            canonical = url.strip()

    account = status.get("account") if isinstance(status.get("account"), dict) else {}
    author_id = str(account.get("id")) if account.get("id") is not None else None
    author_name = account.get("acct") or account.get("username")
    if author_name is not None:
        author_name = str(author_name)

    published_at = _parse_ts(status.get("created_at"))
    content = strip_html(status.get("content") if isinstance(status.get("content"), str) else None)
    language = status.get("language") if isinstance(status.get("language"), str) else None

    engagement: dict[str, Any] = {}
    for key in ("replies_count", "reblogs_count", "favourites_count"):
        if isinstance(status.get(key), int):
            engagement[key] = status[key]

    return NormalizedMention(
        source="mastodon",
        external_id=external_id,
        source_url=url if isinstance(url, str) else None,
        author_id=author_id,
        author_name=author_name,
        content=content,
        title=None,
        language=language,
        published_at=published_at,
        collected_at=collected_at,
        engagement=engagement,
        metadata={
            "instance_host": instance_host,
            "visibility": status.get("visibility"),
            "sensitive": status.get("sensitive"),
            "in_reply_to_id": status.get("in_reply_to_id"),
            "search_scope": "instance_local",
        },
        canonical_url=canonical,
        source_version=source_version,
    ).ensure_hashes()


def parse_statuses(
    payload: Any,
    *,
    collected_at: datetime,
    source_version: str,
    instance_host: str,
) -> list[NormalizedMention]:
    if not isinstance(payload, list):
        raise ConnectorError(
            "Mastodon timeline response must be a list",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
            details={"type": type(payload).__name__},
        )
    return [
        parse_status(
            item,
            collected_at=collected_at,
            source_version=source_version,
            instance_host=instance_host,
        )
        for item in payload
    ]


def parse_search_statuses(
    payload: Any,
    *,
    collected_at: datetime,
    source_version: str,
    instance_host: str,
) -> list[NormalizedMention]:
    """Parse /api/v2/search JSON — statuses array only; instance-local results."""
    if not isinstance(payload, dict):
        raise ConnectorError(
            "Mastodon search response must be an object",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )
    statuses = payload.get("statuses")
    if statuses is None:
        raise ConnectorError(
            "Mastodon search response missing statuses",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
            details={"keys": list(payload.keys())},
        )
    return parse_statuses(
        statuses,
        collected_at=collected_at,
        source_version=source_version,
        instance_host=instance_host,
    )


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
