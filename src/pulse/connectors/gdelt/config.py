"""GDELT DOC 2.0 connector configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator


class GDELTConnectorConfig(BaseModel):
    """Public GDELT DOC 2.0 API settings — no auth, rate-limited."""

    base_url: HttpUrl = Field(
        default="https://api.gdeltproject.org/api/v2/doc/doc",
        description="GDELT DOC 2.0 endpoint",
    )
    query: str = Field(
        ...,
        min_length=1,
        description="GDELT query expression (public DOC API syntax)",
    )
    mode: str = Field(default="ArtList")
    format: str = Field(default="json")
    max_records: int = Field(default=50, ge=1, le=250)
    # GDELT DOC datetime format: YYYYMMDDHHMMSS
    start_datetime: str | None = Field(default=None, description="Inclusive start YYYYMMDDHHMMSS")
    end_datetime: str | None = Field(default=None, description="Inclusive end YYYYMMDDHHMMSS")
    sort: str = Field(default="DateDesc")
    source_key: str | None = None
    user_agent: str = Field(
        default="PulseDataEngine/0.1 (+https://github.com/ayoleynikov/ayoleynikov; GDELT)",
    )
    timeout_seconds: float = Field(default=60.0, gt=0, le=180)
    requests_per_second: float = Field(
        default=0.2,
        gt=0,
        le=1.0,
        description="Conservative client-side rate limit (GDELT public API)",
    )
    max_retries: int = Field(default=3, ge=1, le=6)
    timespan: str | None = Field(
        default=None,
        description="Optional GDELT timespan shortcut e.g. 24h, 7d (overrides start/end when set)",
    )

    @field_validator("query")
    @classmethod
    def _non_empty_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "query must not be empty"
            raise ValueError(msg)
        return cleaned

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def _datetime_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) != 14 or not value.isdigit():
            msg = "datetime must be YYYYMMDDHHMMSS"
            raise ValueError(msg)
        return value
