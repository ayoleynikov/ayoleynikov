"""Mastodon per-instance connector configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator


class MastodonConnectorConfig(BaseModel):
    """One Mastodon *instance* — search is never federation-wide."""

    instance_url: HttpUrl = Field(
        ...,
        description="Base URL of a single Mastodon instance (e.g. https://mastodon.social)",
    )
    # Optional bearer for endpoints that require auth (v2 search on many instances).
    # Public timelines/hashtags typically work without a token.
    access_token: SecretStr | None = Field(
        default=None,
        description="Optional OAuth access token for instance-local search APIs",
    )
    hashtag: str | None = Field(
        default=None,
        description="Optional hashtag (without #) for tag timeline search/fetch",
    )
    local_only: bool = Field(
        default=False,
        description="When true, request local=true on public timelines",
    )
    source_key: str | None = None
    user_agent: str = Field(
        default="PulseDataEngine/0.1 (+https://github.com/ayoleynikov/ayoleynikov; Mastodon)",
    )
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    requests_per_second: float = Field(
        default=1.0,
        gt=0,
        le=5.0,
        description="Per-instance client-side rate limit",
    )
    max_retries: int = Field(default=3, ge=1, le=6)
    page_size: int = Field(default=40, ge=1, le=40)
    streaming_enabled: bool = Field(
        default=True,
        description="Whether streaming endpoints may be used for this instance",
    )

    @field_validator("hashtag")
    @classmethod
    def _clean_hashtag(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lstrip("#")
        if not cleaned:
            msg = "hashtag must not be empty when provided"
            raise ValueError(msg)
        return cleaned
