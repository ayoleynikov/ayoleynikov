"""Shared connector SDK types — mentions, capabilities, errors, accounting."""

from __future__ import annotations

import enum
import hashlib
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator


class ConnectorErrorKind(str, enum.Enum):
    """Classified connector failures for retry / ops decisions."""

    CONFIG = "config"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    PARSE = "parse"
    NOT_MODIFIED = "not_modified"
    UNSUPPORTED = "unsupported"


class ConnectorError(Exception):
    """Typed connector failure — never used to silently discard work."""

    def __init__(
        self,
        message: str,
        *,
        kind: ConnectorErrorKind,
        retryable: bool = False,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code
        self.details = details or {}


class ConnectorCapabilities(BaseModel):
    """What a connector can do — never claim coverage it does not provide."""

    search: bool = False
    incremental_fetch: bool = False
    streaming: bool = False
    historical: bool = False
    supports_etag: bool = False
    supports_last_modified: bool = False
    public_only: bool = True
    max_page_size: int | None = None


class CheckpointCursor(BaseModel):
    """Opaque connector cursor persisted between polls."""

    connector: str
    source_key: str
    etag: str | None = None
    last_modified: str | None = None
    cursor_token: str | None = None
    seen_external_ids: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class RequestAccounting(BaseModel):
    """Per-operation request/cost counters for later usage tracking."""

    http_requests: int = 0
    bytes_downloaded: int = 0
    items_fetched: int = 0
    retries: int = 0
    not_modified: bool = False


class NormalizedMention(BaseModel):
    """Canonical mention shape shared across connectors."""

    mention_id: str | None = None
    source: str
    external_id: str
    source_url: str | None = None
    author_id: str | None = None
    author_name: str | None = None
    content: str | None = None
    title: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    engagement: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    canonical_url: str | None = None
    source_version: str = "1"

    @field_validator("published_at", "collected_at")
    @classmethod
    def _ensure_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            msg = "timestamps must be timezone-aware UTC"
            raise ValueError(msg)
        return value.astimezone(tz=value.tzinfo).replace(microsecond=value.microsecond)

    def ensure_hashes(self) -> NormalizedMention:
        """Fill content_hash / mention_id when missing (deterministic)."""
        data = self.model_dump()
        if not data.get("content_hash"):
            payload = f"{self.source}|{self.external_id}|{self.content or ''}|{self.title or ''}"
            data["content_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if not data.get("mention_id"):
            data["mention_id"] = hashlib.sha256(
                f"{self.source}:{self.external_id}".encode()
            ).hexdigest()
        return NormalizedMention.model_validate(data)


class SearchQuery(BaseModel):
    """Generic search request (RSS supports limited keyword filter on titles/content)."""

    query: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)


class SearchResult(BaseModel):
    mentions: list[NormalizedMention]
    next_cursor: CheckpointCursor | None = None
    accounting: RequestAccounting = Field(default_factory=RequestAccounting)
    exhausted: bool = True


class FetchResult(BaseModel):
    mentions: list[NormalizedMention]
    next_cursor: CheckpointCursor | None = None
    accounting: RequestAccounting = Field(default_factory=RequestAccounting)
    not_modified: bool = False


class HealthStatus(BaseModel):
    healthy: bool
    connector: str
    message: str = "ok"
    details: dict[str, Any] = Field(default_factory=dict)


def canonicalize_url(url: str) -> str:
    """Normalize a public URL for dedupe (scheme/host lower, drop fragment, sort query)."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        msg = f"invalid URL for canonicalization: {url!r}"
        raise ConnectorError(msg, kind=ConnectorErrorKind.PARSE, retryable=False)

    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    path = parts.path or "/"
    # Strip trailing slash except for root
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            query,
            "",  # drop fragment
        )
    )
