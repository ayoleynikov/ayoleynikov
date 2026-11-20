"""YouTube Data API v3 connector — search, metadata, comments with quota accounting."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from pulse.connectors.base import BaseConnector
from pulse.connectors.rate_limit import RateLimiter
from pulse.connectors.retry import classify_http_status, with_retries
from pulse.connectors.types import (
    CheckpointCursor,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorErrorKind,
    FetchResult,
    HealthStatus,
    NormalizedMention,
    SearchQuery,
    SearchResult,
)
from pulse.connectors.youtube.config import YouTubeConnectorConfig
from pulse.connectors.youtube.parsing import (
    parse_api_error,
    parse_comment_threads,
    parse_search_items,
    parse_video_items,
)
from pulse.connectors.youtube.quota import QuotaLedger
from pulse.monitoring.metrics_registry import observe_connector_accounting
from pulse.usage.recorder import get_usage_recorder


class YouTubeConnector(BaseConnector):
    """Official YouTube Data API only. Quota is enforced; never assume unlimited access."""

    name: ClassVar[str] = "youtube"
    version: ClassVar[str] = "1.0.0"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        search=True,
        incremental_fetch=True,
        streaming=False,
        historical=True,
        supports_etag=False,
        supports_last_modified=False,
        public_only=True,
        max_page_size=50,
    )
    config_schema: ClassVar[type[YouTubeConnectorConfig]] = YouTubeConnectorConfig

    def __init__(self, config: YouTubeConnectorConfig | dict[str, Any]) -> None:
        super().__init__(config)
        assert isinstance(self.config, YouTubeConnectorConfig)
        self._client = httpx.AsyncClient(
            base_url=str(self.config.base_url).rstrip("/"),
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": self.config.user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._limiter = RateLimiter(rate=self.config.requests_per_second, per_seconds=1.0)
        self.quota = QuotaLedger(
            daily_budget=self.config.daily_quota_units,
            warning_threshold=self.config.quota_warning_threshold,
        )

    def source_key(self) -> str:
        assert isinstance(self.config, YouTubeConnectorConfig)
        if self.config.source_key:
            return self.config.source_key
        q = self.config.default_query or self.config.channel_id or "search"
        return f"youtube:{q}"

    async def search(
        self,
        query: SearchQuery,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> SearchResult:
        assert isinstance(self.config, YouTubeConnectorConfig)
        self.accounting.reset()
        q = (query.query or self.config.default_query or "").strip()
        if not q and not self.config.channel_id:
            raise ConnectorError(
                "YouTube search requires a query or channel_id",
                kind=ConnectorErrorKind.CONFIG,
                retryable=False,
            )

        # Refuse expensive search.list near budget — never assume unlimited search.
        if self.quota.at_warning() and self.quota.would_exceed("search.list"):
            raise ConnectorError(
                "YouTube search refused: daily quota budget nearly exhausted. "
                "Never assume unlimited Data API access.",
                kind=ConnectorErrorKind.RATE_LIMIT,
                retryable=False,
                details=self.quota.snapshot(),
            )

        page_token = cursor.cursor_token if cursor else None
        params: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "maxResults": min(query.limit, self.config.page_size),
            "key": self.config.api_key.get_secret_value(),
        }
        if q:
            params["q"] = q
        if self.config.channel_id:
            params["channelId"] = self.config.channel_id
        if self.config.region_code:
            params["regionCode"] = self.config.region_code
        if self.config.relevance_language:
            params["relevanceLanguage"] = self.config.relevance_language
        if query.since:
            params["publishedAfter"] = query.since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if query.until:
            params["publishedBefore"] = query.until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if page_token:
            params["pageToken"] = page_token

        payload = await self._api_get("search", "search.list", params)
        mentions, next_token = parse_search_items(
            payload,
            collected_at=datetime.now(UTC),
            source_version=self.version,
        )
        if cursor and cursor.seen_external_ids:
            seen = set(cursor.seen_external_ids)
            mentions = [m for m in mentions if m.external_id not in seen]
        self.accounting.record_items(len(mentions))

        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            cursor_token=next_token,
            seen_external_ids=[m.external_id for m in mentions][:500],
            extra={"quota": self.quota.snapshot(), "unlimited_access": False},
        )
        result = SearchResult(
            mentions=mentions[: query.limit],
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            exhausted=next_token is None,
        )
        self._hook_usage("search")
        return result

    async def fetch_updates(
        self,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> FetchResult:
        """Fetch video metadata (and optional comments) for ids in the checkpoint."""
        assert isinstance(self.config, YouTubeConnectorConfig)
        self.accounting.reset()
        video_ids = []
        if cursor and cursor.extra.get("video_ids"):
            video_ids = list(cursor.extra["video_ids"])
        elif cursor and cursor.seen_external_ids:
            video_ids = [
                eid.split(":", 1)[1]
                for eid in cursor.seen_external_ids
                if eid.startswith("video:")
            ]
        if not video_ids:
            # No ids yet — run a bounded search page if default_query set.
            if not self.config.default_query:
                raise ConnectorError(
                    "YouTube fetch_updates needs video_ids on the cursor or default_query",
                    kind=ConnectorErrorKind.CONFIG,
                    retryable=False,
                )
            search = await self.search(
                SearchQuery(query=self.config.default_query, limit=self.config.page_size),
                cursor=None,
            )
            return FetchResult(
                mentions=search.mentions,
                next_cursor=search.next_cursor,
                accounting=search.accounting,
                not_modified=len(search.mentions) == 0,
            )

        mentions = await self.fetch_video_metadata(video_ids[:50])
        if self.config.include_comments and self.config.max_comments_per_video > 0:
            for vid in video_ids[:5]:  # bounded — never unbounded comment crawl
                try:
                    comments, _ = await self.fetch_comments(vid, max_results=self.config.max_comments_per_video)
                    mentions.extend(comments)
                except ConnectorError as exc:
                    if exc.kind == ConnectorErrorKind.PERMANENT:
                        continue
                    raise

        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            cursor_token=cursor.cursor_token if cursor else None,
            seen_external_ids=[m.external_id for m in mentions][:500],
            extra={"video_ids": video_ids, "quota": self.quota.snapshot(), "unlimited_access": False},
        )
        result = FetchResult(
            mentions=mentions,
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            not_modified=False,
        )
        self._hook_usage("fetch_updates")
        return result

    async def fetch_video_metadata(self, video_ids: list[str]) -> list[NormalizedMention]:
        assert isinstance(self.config, YouTubeConnectorConfig)
        if not video_ids:
            return []
        params = {
            "part": "snippet,statistics",
            "id": ",".join(video_ids),
            "maxResults": len(video_ids),
            "key": self.config.api_key.get_secret_value(),
        }
        payload = await self._api_get("videos", "videos.list", params)
        mentions = parse_video_items(
            payload,
            collected_at=datetime.now(UTC),
            source_version=self.version,
        )
        self.accounting.record_items(len(mentions))
        return mentions

    async def fetch_comments(
        self,
        video_id: str,
        *,
        max_results: int = 20,
        page_token: str | None = None,
    ) -> tuple[list[NormalizedMention], str | None]:
        """Fetch comment threads where permitted. Raises if comments disabled."""
        assert isinstance(self.config, YouTubeConnectorConfig)
        params: dict[str, Any] = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max_results,
            "textFormat": "plainText",
            "key": self.config.api_key.get_secret_value(),
        }
        if page_token:
            params["pageToken"] = page_token
        payload = await self._api_get("commentThreads", "commentThreads.list", params)
        mentions, next_token = parse_comment_threads(
            payload,
            collected_at=datetime.now(UTC),
            source_version=self.version,
            video_id=video_id,
        )
        self.accounting.record_items(len(mentions))
        return mentions, next_token

    async def healthcheck(self) -> HealthStatus:
        assert isinstance(self.config, YouTubeConnectorConfig)
        # Cheap channels.list probe (1 quota unit) — still a real API call shape.
        try:
            params = {
                "part": "snippet",
                "mine": "false",
                "id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Google Developers (public)
                "key": self.config.api_key.get_secret_value(),
            }
            await self._api_get("channels", "channels.list", params)
            return HealthStatus(
                healthy=True,
                connector=self.name,
                message="ok",
                details={
                    "quota": self.quota.snapshot(),
                    "unlimited_access": False,
                    "api": "youtube_data_v3",
                },
            )
        except ConnectorError as exc:
            return HealthStatus(
                healthy=False,
                connector=self.name,
                message=str(exc),
                details={"kind": exc.kind.value, "quota": self.quota.snapshot()},
            )
        except httpx.HTTPError as exc:
            return HealthStatus(healthy=False, connector=self.name, message=str(exc))

    async def close(self) -> None:
        await self._client.aclose()

    async def _api_get(self, path: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert isinstance(self.config, YouTubeConnectorConfig)
        # Charge before the call so concurrent work cannot oversubscribe the budget.
        units = self.quota.charge(method)

        async def _do_get() -> httpx.Response:
            await self._limiter.acquire()
            return await self._client.get(f"/{path}", params=params)

        try:
            response = await with_retries(
                _do_get,
                max_attempts=self.config.max_retries,
                on_retry=self.accounting.record_retry,
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"YouTube HTTP failure: {exc}",
                kind=ConnectorErrorKind.TRANSIENT,
                retryable=True,
            ) from exc

        body = response.content or b""
        self.accounting.record_http(bytes_downloaded=len(body))
        # ``units`` already charged on QuotaLedger; usage hook reads quota.snapshot().
        _ = units

        if response.status_code >= 400:
            try:
                err_payload = response.json()
            except ValueError:
                raise classify_http_status(
                    response.status_code,
                    body[:200].decode("utf-8", errors="replace"),
                ) from None
            if isinstance(err_payload, dict) and "error" in err_payload:
                raise parse_api_error(err_payload["error"])
            raise classify_http_status(
                response.status_code,
                body[:200].decode("utf-8", errors="replace"),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError(
                f"YouTube invalid JSON: {exc}",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            ) from exc
        if not isinstance(payload, dict):
            raise ConnectorError(
                "YouTube response must be an object",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            )
        return payload

    def _hook_usage(self, operation: str) -> None:
        snap = self.accounting.snapshot()
        observe_connector_accounting(
            source=self.name,
            operation=operation,
            http_requests=snap.http_requests,
            bytes_downloaded=snap.bytes_downloaded,
            items_fetched=snap.items_fetched,
            retries=snap.retries,
        )
        get_usage_recorder().record_from_accounting(
            snap,
            source=self.name,
            operation=operation,
            extras={
                "quota": self.quota.snapshot(),
                "unlimited_access": False,
                "api": "youtube_data_v3",
            },
        )
