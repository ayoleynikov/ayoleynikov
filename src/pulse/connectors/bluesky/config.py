"""Bluesky Jetstream configuration — regional endpoints and reconnect policy."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Public Jetstream hosts (no auth). Prefer regional failover lists.
REGIONAL_ENDPOINTS: dict[str, str] = {
    "us-east-1": "wss://jetstream1.us-east.bsky.network/subscribe",
    "us-east-2": "wss://jetstream2.us-east.bsky.network/subscribe",
    "us-west-1": "wss://jetstream1.us-west.bsky.network/subscribe",
    "us-west-2": "wss://jetstream2.us-west.bsky.network/subscribe",
    # Canonical Jetstream v2 XRPC stream (proposal-0015 framing).
    "us-west-v2": (
        "wss://jetstream.us-west.bsky.network"
        "/xrpc/network.bsky.jetstream.subscribeEvents"
    ),
}

DEFAULT_ENDPOINT_ORDER = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "us-west-v2",
]


class BlueskyJetstreamConfig(BaseModel):
    """Configuration for the Bluesky Jetstream consumer."""

    endpoints: list[str] = Field(
        default_factory=lambda: [REGIONAL_ENDPOINTS[k] for k in DEFAULT_ENDPOINT_ORDER],
        description="Ordered WebSocket endpoints for failover",
    )
    region: str | None = Field(
        default=None,
        description="Optional region key from REGIONAL_ENDPOINTS to put first",
    )
    collections: list[str] = Field(
        default_factory=lambda: ["app.bsky.feed.post"],
        description="ATProto collections to subscribe to (posts by default)",
    )
    kinds: list[str] = Field(
        default_factory=lambda: ["commit"],
        description="Jetstream v2 kinds filter (ignored on legacy /subscribe)",
    )
    source_key: str = Field(default="bluesky:jetstream", min_length=1)
    max_message_bytes: int = Field(default=2_000_000, ge=1024)
    reconnect_initial_seconds: float = Field(default=1.0, gt=0, le=60)
    reconnect_max_seconds: float = Field(default=60.0, gt=0, le=600)
    reconnect_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    cursor_rewind_us: int = Field(
        default=0,
        ge=0,
        description="Optional microseconds to rewind timestamp cursor on reconnect",
    )
    user_agent: str = Field(
        default="PulseDataEngine/0.1 (+https://github.com/ayoleynikov/ayoleynikov; Jetstream)",
    )

    @field_validator("endpoints")
    @classmethod
    def _non_empty_endpoints(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if not cleaned:
            msg = "endpoints must not be empty"
            raise ValueError(msg)
        for url in cleaned:
            if not url.startswith(("ws://", "wss://")):
                msg = f"endpoint must be ws(s) URL: {url}"
                raise ValueError(msg)
        return cleaned

    def ordered_endpoints(self) -> list[str]:
        """Return endpoints with optional preferred region first."""
        endpoints = list(self.endpoints)
        if self.region and self.region in REGIONAL_ENDPOINTS:
            preferred = REGIONAL_ENDPOINTS[self.region]
            endpoints = [preferred, *[e for e in endpoints if e != preferred]]
        return endpoints

    def is_v2_endpoint(self, endpoint: str) -> bool:
        return "subscribeEvents" in endpoint or "/xrpc/" in endpoint
