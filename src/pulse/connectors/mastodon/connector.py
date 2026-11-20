"""Mastodon per-instance connector — public timelines, tag search, optional streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from pulse.connectors.base import BaseConnector
from pulse.connectors.mastodon.config import MastodonConnectorConfig
from pulse.connectors.mastodon.parsing import parse_search_statuses, parse_statuses, parse_status
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
from pulse.monitoring.metrics_registry import observe_connector_accounting
from pulse.usage.recorder import get_usage_recorder


class MastodonConnector(BaseConnector):
    """Public Mastodon client bound to a single instance.

    Capabilities are instance-scoped. This connector never claims federation-wide
    search — results come only from the configured ``instance_url``.
    """

    name: ClassVar[str] = "mastodon"
    version: ClassVar[str] = "1.0.0"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        search=True,
        incremental_fetch=True,
        streaming=True,
        historical=False,
        supports_etag=False,
        supports_last_modified=False,
        public_only=True,
        max_page_size=40,
    )
    config_schema: ClassVar[type[MastodonConnectorConfig]] = MastodonConnectorConfig

    def __init__(self, config: MastodonConnectorConfig | dict[str, Any]) -> None:
        super().__init__(config)
        assert isinstance(self.config, MastodonConnectorConfig)
        headers = {"User-Agent": self.config.user_agent, "Accept": "application/json"}
        if self.config.access_token is not None:
            headers["Authorization"] = (
                f"Bearer {self.config.access_token.get_secret_value()}"
            )
        self._client = httpx.AsyncClient(
            base_url=str(self.config.instance_url).rstrip("/"),
            timeout=self.config.timeout_seconds,
            headers=headers,
            follow_redirects=True,
        )
        self._limiter = RateLimiter(rate=self.config.requests_per_second, per_seconds=1.0)

    def source_key(self) -> str:
        assert isinstance(self.config, MastodonConnectorConfig)
        if self.config.source_key:
            return self.config.source_key
        host = self.instance_host
        tag = self.config.hashtag or "public"
        return f"mastodon:{host}:{tag}"

    @property
    def instance_host(self) -> str:
        assert isinstance(self.config, MastodonConnectorConfig)
        host = urlparse(str(self.config.instance_url)).hostname
        return host or "unknown"

    async def search(
        self,
        query: SearchQuery,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> SearchResult:
        """Instance-local search only — never federation-wide.

        Prefer hashtag timeline when ``hashtag`` / query looks like a tag;
        otherwise use ``/api/v2/search`` (requires token on many instances).
        """
        assert isinstance(self.config, MastodonConnectorConfig)
        self.accounting.reset()
        limit = min(query.limit, self.config.page_size)
        tag = self._resolve_hashtag(query.query)
        max_id = cursor.cursor_token if cursor and cursor.cursor_token else None

        if tag:
            path = f"/api/v1/timelines/tag/{tag}"
            params: dict[str, Any] = {"limit": limit}
            if max_id:
                params["max_id"] = max_id
            if self.config.local_only:
                params["local"] = "true"
            payload = await self._get_json(path, params=params)
            mentions = parse_statuses(
                payload,
                collected_at=datetime.now(UTC),
                source_version=self.version,
                instance_host=self.instance_host,
            )
        else:
            q = (query.query or "").strip()
            if not q:
                raise ConnectorError(
                    "Mastodon search requires a query or configured hashtag "
                    "(instance-local only; not federation-wide)",
                    kind=ConnectorErrorKind.CONFIG,
                    retryable=False,
                )
            if self.config.access_token is None:
                raise ConnectorError(
                    "Mastodon /api/v2/search typically requires an access_token on this "
                    "instance; configure hashtag for public tag timelines instead. "
                    "Search is instance-local — not federation-wide.",
                    kind=ConnectorErrorKind.AUTH,
                    retryable=False,
                )
            params = {"q": q, "type": "statuses", "limit": limit, "resolve": "false"}
            if max_id:
                params["offset"] = max_id  # v2 search uses offset pagination when provided
            payload = await self._get_json("/api/v2/search", params=params)
            mentions = parse_search_statuses(
                payload,
                collected_at=datetime.now(UTC),
                source_version=self.version,
                instance_host=self.instance_host,
            )

        if cursor and cursor.seen_external_ids:
            seen = set(cursor.seen_external_ids)
            mentions = [m for m in mentions if m.external_id not in seen]
        self.accounting.record_items(len(mentions))
        next_token = _oldest_status_id(mentions)
        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            cursor_token=next_token,
            seen_external_ids=[m.external_id for m in mentions][:500],
            extra={
                "instance_host": self.instance_host,
                "search_scope": "instance_local",
                "federation_wide_search": False,
            },
        )
        result = SearchResult(
            mentions=mentions[:limit],
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            exhausted=len(mentions) < limit,
        )
        self._hook_usage("search")
        return result

    async def fetch_updates(
        self,
        *,
        cursor: CheckpointCursor | None = None,
    ) -> FetchResult:
        """Incremental public or hashtag timeline using max_id / since_id checkpoints."""
        assert isinstance(self.config, MastodonConnectorConfig)
        self.accounting.reset()
        if self.config.hashtag:
            path = f"/api/v1/timelines/tag/{self.config.hashtag}"
        else:
            path = "/api/v1/timelines/public"
        params: dict[str, Any] = {"limit": self.config.page_size}
        if self.config.local_only:
            params["local"] = "true"
        if cursor and cursor.extra.get("since_id"):
            params["since_id"] = cursor.extra["since_id"]
        elif cursor and cursor.cursor_token:
            params["max_id"] = cursor.cursor_token

        payload = await self._get_json(path, params=params)
        mentions = parse_statuses(
            payload,
            collected_at=datetime.now(UTC),
            source_version=self.version,
            instance_host=self.instance_host,
        )
        if cursor and cursor.seen_external_ids:
            seen = set(cursor.seen_external_ids)
            mentions = [m for m in mentions if m.external_id not in seen]
        self.accounting.record_items(len(mentions))

        newest = _newest_status_id(mentions) or (
            str(cursor.extra.get("since_id")) if cursor and cursor.extra.get("since_id") else None
        )
        next_cursor = CheckpointCursor(
            connector=self.name,
            source_key=self.source_key(),
            cursor_token=_oldest_status_id(mentions),
            seen_external_ids=[m.external_id for m in mentions][:500],
            extra={
                "since_id": newest,
                "instance_host": self.instance_host,
                "search_scope": "instance_local",
            },
        )
        result = FetchResult(
            mentions=mentions,
            next_cursor=next_cursor,
            accounting=self.accounting.snapshot(),
            not_modified=len(mentions) == 0,
        )
        self._hook_usage("fetch_updates")
        return result

    async def stream_public(self) -> AsyncIterator[NormalizedMention]:
        """Consume instance public streaming API (SSE) when enabled.

        Instance-scoped only — not a federation firehose.
        """
        assert isinstance(self.config, MastodonConnectorConfig)
        if not self.config.streaming_enabled:
            raise ConnectorError(
                "streaming disabled for this Mastodon instance config",
                kind=ConnectorErrorKind.UNSUPPORTED,
                retryable=False,
            )
        # Prefer SSE public stream; WebSocket variants differ by instance.
        path = "/api/v1/streaming/public"
        if self.config.local_only:
            path = "/api/v1/streaming/public/local"

        await self._limiter.acquire()
        async with self._client.stream("GET", path, headers={"Accept": "text/event-stream"}) as resp:
            self.accounting.record_http(bytes_downloaded=0)
            if resp.status_code >= 400:
                body = (await resp.aread())[:200].decode("utf-8", errors="replace")
                raise classify_http_status(resp.status_code, body)
            event_name = "update"
            data_lines: list[str] = []
            async for line in resp.aiter_lines():
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip() or "update"
                    continue
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
                    continue
                if line == "" and data_lines:
                    raw = "\n".join(data_lines)
                    data_lines = []
                    if event_name != "update":
                        event_name = "update"
                        continue
                    try:
                        import orjson

                        payload = orjson.loads(raw)
                    except Exception as exc:  # noqa: BLE001
                        raise ConnectorError(
                            f"invalid Mastodon stream JSON: {exc}",
                            kind=ConnectorErrorKind.PARSE,
                            retryable=False,
                        ) from exc
                    mention = parse_status(
                        payload,
                        collected_at=datetime.now(UTC),
                        source_version=self.version,
                        instance_host=self.instance_host,
                    )
                    self.accounting.record_items(1)
                    yield mention

    async def healthcheck(self) -> HealthStatus:
        assert isinstance(self.config, MastodonConnectorConfig)
        try:
            await self._limiter.acquire()
            response = await self._client.get("/api/v1/instance")
            self.accounting.record_http(bytes_downloaded=len(response.content or b""))
            if response.status_code >= 400:
                return HealthStatus(
                    healthy=False,
                    connector=self.name,
                    message=f"HTTP {response.status_code}",
                    details={
                        "status_code": response.status_code,
                        "instance_host": self.instance_host,
                        "federation_wide_search": False,
                    },
                )
            payload = response.json()
            title = payload.get("title") if isinstance(payload, dict) else None
            return HealthStatus(
                healthy=True,
                connector=self.name,
                message="ok",
                details={
                    "instance_host": self.instance_host,
                    "title": title,
                    "federation_wide_search": False,
                    "search_scope": "instance_local",
                    "streaming_enabled": self.config.streaming_enabled,
                },
            )
        except httpx.HTTPError as exc:
            return HealthStatus(
                healthy=False,
                connector=self.name,
                message=str(exc),
                details={"instance_host": self.instance_host},
            )

    async def close(self) -> None:
        await self._client.aclose()

    def _resolve_hashtag(self, query: str | None) -> str | None:
        assert isinstance(self.config, MastodonConnectorConfig)
        if query and query.strip().startswith("#"):
            return query.strip().lstrip("#")
        if query and " " not in query.strip() and self.config.hashtag is None:
            # Bare token treated as hashtag for public tag timeline (no auth).
            return query.strip().lstrip("#") or None
        return self.config.hashtag

    async def _get_json(self, path: str, *, params: dict[str, Any]) -> Any:
        assert isinstance(self.config, MastodonConnectorConfig)

        async def _do_get() -> httpx.Response:
            await self._limiter.acquire()
            return await self._client.get(path, params=params)

        try:
            response = await with_retries(
                _do_get,
                max_attempts=self.config.max_retries,
                on_retry=self.accounting.record_retry,
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"Mastodon HTTP failure: {exc}",
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
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorError(
                f"Mastodon invalid JSON: {exc}",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            ) from exc

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
                "instance_host": self.instance_host,
                "search_scope": "instance_local",
                "federation_wide_search": False,
            },
        )


def _oldest_status_id(mentions: list[NormalizedMention]) -> str | None:
    if not mentions:
        return None
    # external_id is host:id — Mastodon pagination wants the numeric id.
    last = mentions[-1].external_id
    return last.rsplit(":", 1)[-1]


def _newest_status_id(mentions: list[NormalizedMention]) -> str | None:
    if not mentions:
        return None
    first = mentions[0].external_id
    return first.rsplit(":", 1)[-1]
