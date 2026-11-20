"""Health and readiness endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pulse import __version__
from pulse.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    version: str
    service: str
    checks: dict[str, Any] = Field(default_factory=dict)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — process is up."""
    return HealthResponse(status="ok", version=__version__, service="pulse-api")


@router.get("/ready", response_model=ReadinessResponse)
async def ready() -> ReadinessResponse:
    """Readiness probe — config loaded; deeper dependency checks land with auth later."""
    settings = get_settings()
    return ReadinessResponse(
        status="ok",
        version=__version__,
        service="pulse-api",
        checks={
            "config": "ok",
            "env": settings.env,
            "clickhouse_enabled": settings.clickhouse_enabled,
            "note": "Postgres/Redis/ClickHouse connectivity probes expand with auth later.",
        },
    )
