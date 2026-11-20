"""GDELT DOC 2.0 connector — historical search with time windows and pagination."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import httpx

from pulse.connectors.base import BaseConnector
from pulse.connectors.gdelt.config import GDELTConnectorConfig
from pulse.connectors.gdelt.parsing import parse_artlist_response
from pulse.connectors.rate_limit import RateLimiter
from pulse.connectors.retry import classify_http_status, with_retries
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorErrorKind,
    FetchResult,
    HealthStatus,
    SearchQuery,
    SearchResult,
)


class GDELTConnector(BaseConnector):
    """Public GDELT DOC 2.0 client. Does not fabricate results on empty/error."""

    name: ClassVar[str] = "gdelt"
    version: ClassVar[str] = "1.0.0"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        search=True,
        incremental_fetch=True,
        streaming=False,
        historical=True,
        supports_etag=False,
        supports_last_modified=False,
        public_only=True,
        max_page_size=250,
    )
    config_schema: ClassVar[type[GDELTConnectorConfig]] = GDELTConnectorConfig

    def __init__(self, config: GDELTConnectorConfig | dict[str, Any]) -> None:
        super().__init__(config)
        assert isinstance(self.config, GDELTConnectorConfig)
        self._client = httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": self.config.user_agent},
            follow_redirects=True,
        )
        self._limiter = RateLimiter(rate=self.config.requests_per_second, per_seconds=1.0)

    def source_key(self) -> str:
        assert isinstance(self.config, GDELTConnectorConfig)
        if self.config.source_key:
            return self.config.source_key
        return f"gdelt:{self.config.query}"

    def build_params(
        self,
        *,
        query: str | None = None,
        start: str | None = None,
        end: str | None = None,
        max_records: int | None = None,
        timespan: str | None = None,
    ) -> dict[str, str]:
        assert isinstance(self.config, GDELTConnectorConfig)
        params: dict[str, str] = {
            "query": query or self.config.query,
            "mode": self.config.mode,
            "format": self.config.format,
            "maxrecords": str(max_records or self.config.max_records),
            "sort": self.config.sort,
        }
        ts = timespan if timespan is not None else self.config.timespan
        if ts:
            params["timespan"] = ts
        else:
            start_v = start if start is not None else self.config.start_datetime
            end_v = end if end is not None else self.config.end_datetime
            if start_v:
                params["startdatetime"] = start_v
            if end_v:
                params["enddatetime"] = end_v
        return params

    async def search(
        self,
        query: SearchQuery,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> SearchResult:
        assert isinstance(self.config, GDELTConnectorConfig)
        self.accounting.reset()
        q = query.query or self.config.query
        start = _fmt_gdelt(query.since) if query.since else None
        end = _fmt_gdelt(query.until) if query.until else None
        # Pagination via cursor_token holding last enddatetime watermark.
        if cursor and cursor.cursor_token and not end:
            end = cursor.cursor_token

        result = await self._fetch_page(
            params=self.build_params(
                query=q,
                start=start,
                end=end,
                max_records=min(query.limit, self.config.max_records),
            )
        )
        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            cursor_token=end or (cursor.cursor_token if cursor else None),
            seen_external_ids=[m.external_id for m in result][:500],
            extra={"page_count": len(result)},
        )
        # Filter already-seen URLs when cursor provided.
        if cursor and cursor.seen_external_ids:
            seen = set(cursor.seen_external_ids)
            filtered = [m for m in result if m.external_id not in seen]
        else:
            filtered = result
        self.accounting.record_items(len(filtered))
        return SearchResult(
            mentions=filtered[: query.limit],
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            exhausted=len(result) < (min(query.limit, self.config.max_records)),
        )

    async def fetch_updates(
        self,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> FetchResult:
        """Incremental windowed fetch ending at now; cursor stores watermark."""
        assert isinstance(self.config, GDELTConnectorConfig)
        self.accounting.reset()
        end_dt = datetime.now(UTC)
        if cursor and cursor.extra.get("watermark"):
            start_dt = datetime.fromisoformat(str(cursor.extra["watermark"]))
        elif self.config.start_datetime:
            start_dt = datetime.strptime(self.config.start_datetime, "%Y%m%d%H%M%S").replace(
                tzinfo=UTC
            )
        else:
            start_dt = end_dt - timedelta(hours=24)

        params = self.build_params(
            start=_fmt_gdelt(start_dt),
            end=_fmt_gdelt(end_dt),
        )
        mentions = await self._fetch_page(params=params)
        if cursor and cursor.seen_external_ids:
            seen = set(cursor.seen_external_ids)
            mentions = [m for m in mentions if m.external_id not in seen]
        self.accounting.record_items(len(mentions))
        seen_ids = [m.external_id for m in mentions]
        if cursor:
            seen_ids = list(dict.fromkeys([*seen_ids, *cursor.seen_external_ids]))[:500]
        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            cursor_token=_fmt_gdelt(end_dt),
            seen_external_ids=seen_ids,
            extra={"watermark": end_dt.isoformat()},
        )
        return FetchResult(
            mentions=mentions,
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            not_modified=False,
        )

    async def healthcheck(self) -> HealthStatus:
        assert isinstance(self.config, GDELTConnectorConfig)
        # Lightweight probe: maxrecords=1 with a tiny timespan — still a real public call.
        try:
            await self._limiter.acquire()
            response = await self._client.get(
                str(self.config.base_url),
                params={
                    "query": "pulse",
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": "1",
                    "timespan": "1d",
                },
            )
            self.accounting.record_http(bytes_downloaded=len(response.content or b""))
            healthy = response.status_code < 500
            return HealthStatus(
                healthy=healthy,
                connector=self.name,
                message="ok" if healthy else f"HTTP {response.status_code}",
                details={"status_code": response.status_code},
            )
        except httpx.HTTPError as exc:
            return HealthStatus(healthy=False, connector=self.name, message=str(exc))

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_page(self, *, params: dict[str, str]) -> list:
        assert isinstance(self.config, GDELTConnectorConfig)
        url = str(self.config.base_url)

        async def _do_get() -> httpx.Response:
            await self._limiter.acquire()
            return await self._client.get(url, params=params)

        try:
            response = await with_retries(
                _do_get,
                max_attempts=self.config.max_retries,
                on_retry=self.accounting.record_retry,
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"GDELT HTTP failure: {exc}",
                kind=ConnectorErrorKind.TRANSIENT,
                retryable=True,
            ) from exc

        body = response.content or b""
        self.accounting.record_http(bytes_downloaded=len(body))
        if response.status_code >= 400:
            raise classify_http_status(
                response.status_code,
                body[:200].decode("utf-8", errors="replace"),
            )

        # GDELT sometimes returns empty body or HTML when overloaded — fail loudly.
        text = body.decode("utf-8", errors="replace").strip()
        if not text:
            raise ConnectorError(
                "GDELT returned empty body",
                kind=ConnectorErrorKind.TRANSIENT,
                retryable=True,
            )
        if text.startswith("<"):
            raise ConnectorError(
                "GDELT returned HTML instead of JSON (rate limit or outage)",
                kind=ConnectorErrorKind.RATE_LIMIT,
                retryable=True,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                f"GDELT invalid JSON: {exc}",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            ) from exc

        return parse_artlist_response(
            payload,
            collected_at=datetime.now(UTC),
            source_version=self.version,
        )


def _fmt_gdelt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S")
