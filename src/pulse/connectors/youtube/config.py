"""YouTube Data API v3 connector configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator


class YouTubeConnectorConfig(BaseModel):
    """Official YouTube Data API v3 settings — quota-limited, never unlimited."""

    api_key: SecretStr = Field(
        ...,
        description="YouTube Data API key (required; never logged)",
    )
    base_url: HttpUrl = Field(
        default="https://www.googleapis.com/youtube/v3",
        description="YouTube Data API v3 base URL",
    )
    default_query: str | None = Field(
        default=None,
        description="Default search query when SearchQuery.query is omitted",
    )
    channel_id: str | None = Field(
        default=None,
        description="Optional channel filter for search/list",
    )
    region_code: str | None = Field(default=None, max_length=2)
    relevance_language: str | None = Field(default=None, max_length=8)
    include_comments: bool = Field(
        default=True,
        description="Fetch comment threads when comments are permitted for a video",
    )
    max_comments_per_video: int = Field(default=20, ge=0, le=100)
    source_key: str | None = None
    user_agent: str = Field(
        default="PulseDataEngine/0.1 (+https://github.com/ayoleynikov/ayoleynikov; YouTube)",
    )
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    requests_per_second: float = Field(
        default=2.0,
        gt=0,
        le=10.0,
        description="Client-side request pacing (quota is separate and authoritative)",
    )
    max_retries: int = Field(default=3, ge=1, le=6)
    page_size: int = Field(default=25, ge=1, le=50)
    # Daily quota budget for THIS connector instance — never assume unlimited.
    daily_quota_units: int = Field(
        default=10_000,
        ge=1,
        description="Configured daily quota budget (default mirrors common free tier)",
    )
    quota_warning_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Fraction of daily budget at which searches are refused",
    )

    @field_validator("api_key")
    @classmethod
    def _non_empty_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            msg = "api_key must not be empty"
            raise ValueError(msg)
        return value
