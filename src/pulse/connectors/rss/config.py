"""RSS/Atom connector configuration schema."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator


class RSSConnectorConfig(BaseModel):
    """Configuration for a single public RSS/Atom feed."""

    feed_url: HttpUrl
    source_key: str | None = Field(
        default=None,
        description="Checkpoint key; defaults to canonical feed URL",
    )
    user_agent: str = Field(
        default="PulseDataEngine/0.1 (+https://github.com/ayoleynikov/ayoleynikov; RSS)",
    )
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_entries: int = Field(default=100, ge=1, le=500)
    requests_per_second: float = Field(default=1.0, gt=0, le=10)
    max_retries: int = Field(default=3, ge=1, le=8)

    @field_validator("user_agent")
    @classmethod
    def _non_empty_ua(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "user_agent must not be empty"
            raise ValueError(msg)
        return cleaned
