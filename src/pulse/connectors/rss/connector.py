"""RSS/Atom connector — public feed polling with ETag / Last-Modified."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from pulse.connectors.base import BaseConnector
from pulse.connectors.rate_limit import RateLimiter
from pulse.connectors.retry import classify_http_status, with_retries
from pulse.connectors.rss.config import RSSConnectorConfig
from pulse.connectors.rss.parsing import parse_feed
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorErrorKind,
    FetchResult,
    HealthStatus,
    SearchQuery,
    SearchResult,
    canonicalize_url,
)


class RSSConnector(BaseConnector):
    """Poll a single public RSS or Atom feed."""

    name: ClassVar[str] = "rss"
    version: ClassVar[str] = "1.0.0"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        search=True,
        incremental_fetch=True,
        streaming=False,
        historical=False,
        supports_etag=True,
        supports_last_modified=True,
        public_only=True,
        max_page_size=500,
    )
    config_schema: ClassVar[type[RSSConnectorConfig]] = RSSConnectorConfig

    def __init__(self, config: RSSConnectorConfig | dict[str, Any]) -> None:
        super().__init__(config)
        assert isinstance(self.config, RSSConnectorConfig)
        self._client = httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": self.config.user_agent},
            follow_redirects=True,
        )
        self._limiter = RateLimiter(rate=self.config.requests_per_second, per_seconds=1.0)

    def source_key(self) -> str:
        assert isinstance(self.config, RSSConnectorConfig)
        if self.config.source_key:
            return self.config.source_key
        return canonicalize_url(str(self.config.feed_url))

    async def search(
        self,
        query: SearchQuery,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> SearchResult:
        """Fetch the feed and optionally filter by keyword (title/content)."""
        result = await self.fetch_updates(cursor=cursor)
        mentions = result.mentions
        if query.query:
            needle = query.query.casefold()
            mentions = [
                m
                for m in mentions
                if (m.title and needle in m.title.casefold())
                or (m.content and needle in m.content.casefold())
            ]
        if query.since:
            mentions = [m for m in mentions if m.published_at and m.published_at >= query.since]
        if query.until:
            mentions = [m for m in mentions if m.published_at and m.published_at <= query.until]
        mentions = mentions[: query.limit]
        return SearchResult(
            mentions=mentions,
            next_cursor=result.next_cursor,
            accounting=result.accounting,
            exhausted=True,
        )

    async def fetch_updates(
        self,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> FetchResult:
        assert isinstance(self.config, RSSConnectorConfig)
        self.accounting.reset()
        feed_url = str(self.config.feed_url)
        headers: dict[str, str] = {}
        if cursor and cursor.etag:
            headers["If-None-Match"] = cursor.etag
        if cursor and cursor.last_modified:
            headers["If-Modified-Since"] = cursor.last_modified

        async def _do_get() -> httpx.Response:
            await self._limiter.acquire()
            return await self._client.get(feed_url, headers=headers)

        try:
            response = await with_retries(
                _do_get,
                max_attempts=self.config.max_retries,
                on_retry=self.accounting.record_retry,
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"HTTP failure fetching {feed_url}: {exc}",
                kind=ConnectorErrorKind.TRANSIENT,
                retryable=True,
            ) from exc

        body = response.content or b""
        self.accounting.record_http(bytes_downloaded=len(body))

        if response.status_code == 304:
            self.accounting.mark_not_modified()
            next_cursor = CheckpointCursor(
                connector=self.name,
                source_key=self.source_key(),
                etag=(cursor.etag if cursor else None) or response.headers.get("ETag"),
                last_modified=(cursor.last_modified if cursor else None)
                or response.headers.get("Last-Modified"),
                seen_external_ids=list(cursor.seen_external_ids) if cursor else [],
                extra=dict(cursor.extra) if cursor else {},
            )
            return FetchResult(
                mentions=[],
                next_cursor=next_cursor,
                accounting=self.accounting.snapshot(),
                not_modified=True,
            )

        if response.status_code >= 400:
            preview = body[:200].decode("utf-8", errors="replace")
            raise classify_http_status(response.status_code, preview)

        collected_at = datetime.now(UTC)
        mentions, meta = parse_feed(
            body,
            feed_url=feed_url,
            collected_at=collected_at,
            source_version=self.version,
            max_entries=self.config.max_entries,
        )

        # Incremental: drop entries already seen (by external_id).
        seen = set(cursor.seen_external_ids) if cursor else set()
        new_mentions = [m for m in mentions if m.external_id not in seen]
        # Keep a bounded window of recent IDs for the next poll.
        recent_ids = [m.external_id for m in mentions][:200]
        merged_seen = list(dict.fromkeys([*recent_ids, *list(seen)]))[:500]

        self.accounting.record_items(len(new_mentions))
        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            etag=response.headers.get("ETag") or (cursor.etag if cursor else None),
            last_modified=response.headers.get("Last-Modified")
            or (cursor.last_modified if cursor else None),
            seen_external_ids=merged_seen,
            extra={"feed_meta": meta},
        )
        return FetchResult(
            mentions=new_mentions,
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            not_modified=False,
        )

    async def healthcheck(self) -> HealthStatus:
        assert isinstance(self.config, RSSConnectorConfig)
        feed_url = str(self.config.feed_url)
        try:
            await self._limiter.acquire()
            response = await self._client.head(feed_url)
            # Some feeds reject HEAD — fall back to GET with no body expectation.
            if response.status_code in {405, 501}:
                response = await self._client.get(feed_url, headers={"Range": "bytes=0-0"})
            self.accounting.record_http(bytes_downloaded=len(response.content or b""))
            if response.status_code >= 400 and response.status_code != 416:
                return HealthStatus(
                    healthy=False,
                    connector=self.name,
                    message=f"HTTP {response.status_code}",
                    details={"feed_url": feed_url},
                )
            return HealthStatus(
                healthy=True,
                connector=self.name,
                message="ok",
                details={"feed_url": feed_url, "status_code": response.status_code},
            )
        except httpx.HTTPError as exc:
            return HealthStatus(
                healthy=False,
                connector=self.name,
                message=str(exc),
                details={"feed_url": feed_url},
            )

    async def close(self) -> None:
        await self._client.aclose()
