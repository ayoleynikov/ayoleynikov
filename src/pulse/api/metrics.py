"""Prometheus metrics stub endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest

router = APIRouter(tags=["metrics"])

# Process-local registry so tests do not collide with default collectors.
REGISTRY = CollectorRegistry()
REQUESTS_TOTAL = Counter(
    "pulse_http_requests_total",
    "Total HTTP requests handled by Pulse API (stub counter).",
    ["method", "path", "status"],
    registry=REGISTRY,
)


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus text exposition format (stub — expand in Phase 7)."""
    payload = generate_latest(REGISTRY)
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
