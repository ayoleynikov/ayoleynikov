"""Smoke tests for health and metrics endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "pulse-api"
    assert "version" in body


def test_metrics_stub(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    # Prometheus exposition format (may be empty registry beyond HELP/TYPE).
    assert isinstance(response.content, bytes)
