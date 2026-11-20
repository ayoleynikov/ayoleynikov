"""API smoke tests for connector registry endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_connectors(client: TestClient) -> None:
    response = client.get("/api/v1/connectors")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body}
    assert "rss" in names
    assert "bluesky" in names
    assert "gdelt" in names
    assert "mastodon" in names
    assert "youtube" in names
    assert "reddit" not in names


def test_rss_poll_validates(client: TestClient) -> None:
    response = client.post(
        "/api/v1/connectors/rss/poll",
        json={"feed_url": "https://example.com/feed.xml"},
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "validated"
    assert "Celery" in response.json()["note"] or "pulse-poll-rss" in response.json()["note"]
