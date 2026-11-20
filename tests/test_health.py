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


def test_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert isinstance(response.content, bytes)
    # Phase 7 registers connector / ingestion / queue / cost series (may be zeroed).
    text = response.text
    assert "pulse_http_requests_total" in text or "pulse_connector_requests_total" in text or text == ""


def test_ready_ok(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "checks" in body
