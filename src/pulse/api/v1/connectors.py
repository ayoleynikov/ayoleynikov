"""Connector registry API (Phase 2 — read-only manifest + RSS poll trigger stub)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from pulse.connectors.registry import get_registry

router = APIRouter(prefix="/connectors", tags=["connectors"])


class ConnectorManifestItem(BaseModel):
    name: str
    version: str
    capabilities: dict[str, Any]
    policies: dict[str, Any]


class PollRSSRequest(BaseModel):
    feed_url: HttpUrl
    project_id: str | None = None
    source_key: str | None = None


class PollRSSAccepted(BaseModel):
    detail: str
    task: str = "pulse.workers.tasks.poll_rss_feed"
    feed_url: str
    note: str = (
        "Enqueue via Celery worker or run `pulse-poll-rss <url>` locally. "
        "This endpoint validates input and returns enqueue instructions in Phase 2."
    )


@router.get("", response_model=list[ConnectorManifestItem])
async def list_connectors() -> list[ConnectorManifestItem]:
    """List registered connectors, capabilities, and policies."""
    registry = get_registry()
    return [
        ConnectorManifestItem(
            name=item.name,
            version=item.version,
            capabilities=item.capabilities.model_dump(),
            policies=item.policies,
        )
        for item in registry.list()
    ]


@router.post("/rss/poll", response_model=PollRSSAccepted)
async def enqueue_rss_poll(body: PollRSSRequest) -> PollRSSAccepted:
    """Validate an RSS poll request.

    Phase 2 does not silently claim collection success from the API alone — callers
    must run the Celery task or CLI against a live DB.
    """
    feed_url = str(body.feed_url)
    if not feed_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="feed_url must be http(s)")
    return PollRSSAccepted(
        detail="validated",
        feed_url=feed_url,
    )


class HealthManifest(BaseModel):
    connectors: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/health", response_model=HealthManifest)
async def connectors_health_manifest() -> HealthManifest:
    """Static capability/health manifest (no live upstream probes)."""
    return HealthManifest(connectors=get_registry().health_manifest())
