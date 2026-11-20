"""API tests for /api/v1/usage and Prometheus usage series."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pulse.config import Settings
from pulse.main import create_app
from pulse.usage.pricing import PricingCatalog
from pulse.usage.recorder import reset_usage_recorder


def _client() -> TestClient:
    reset_usage_recorder(PricingCatalog())
    app = create_app(Settings(env="test", jwt_secret="x" * 32, log_level="WARNING"))
    return TestClient(app)


def test_usage_summary_empty() -> None:
    with _client() as client:
        response = client.get("/api/v1/usage")
        assert response.status_code == 200
        body = response.json()
        assert body["record_count"] == 0
        assert "not verified" in body["pricing_disclaimer"].lower()


def test_record_usage_with_fixture_pricing() -> None:
    with _client() as client:
        loaded = client.post("/api/v1/usage/pricing/fixture")
        assert loaded.status_code == 200
        assert loaded.json()["pricing_label"] == "fixture"
        assert "synthetic" in loaded.json()["disclaimer"].lower()

        created = client.post(
            "/api/v1/usage/records",
            json={
                "source": "rss",
                "operation": "fetch",
                "http_requests": 3,
                "bytes_downloaded": 1_048_576,
                "items_collected": 20,
                "items_accepted": 15,
                "items_rejected": 3,
                "items_duplicates": 2,
                "worker_time_ms": 250,
                "retries": 1,
            },
        )
        assert created.status_code == 200
        record = created.json()
        assert record["source"] == "rss"
        assert float(record["cost_usd"]) > 0
        assert record["pricing_label"] == "fixture"

        summary = client.get("/api/v1/usage").json()
        assert summary["record_count"] == 1
        assert summary["items_accepted"] == 15

        costs = client.get("/api/v1/usage/costs", params={"group_by": "source"})
        assert costs.status_code == 200
        rollups = costs.json()["rollups"]
        assert len(rollups) == 1
        assert rollups[0]["key"] == "rss"
        assert rollups[0]["cost_per_1k_mentions_usd"] is not None

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        text = metrics.text
        assert "pulse_usage_records_total" in text
        assert "pulse_connector_requests_total" in text
        assert "pulse_usage_cost_usd_total" in text


def test_add_operator_pricing_rule() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/usage/pricing",
            json={
                "rule": {
                    "source": "gdelt",
                    "cost_component": "http_request",
                    "unit": "per_1",
                    "unit_price_usd": "0.001",
                    "pricing_label": "operator",
                    "notes": "Operator-configured demo rate",
                }
            },
        )
        assert response.status_code == 200
        rules = response.json()["rules"]
        assert any(r["source"] == "gdelt" and r["pricing_label"] == "operator" for r in rules)


def test_ready_endpoint() -> None:
    with _client() as client:
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["config"] == "ok"
