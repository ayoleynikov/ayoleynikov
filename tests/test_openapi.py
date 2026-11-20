"""OpenAPI and versioned router smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_schema(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Pulse Data Engine"
    paths = schema["paths"]
    assert "/health" in paths
    assert "/metrics" in paths
    assert "/api/v1/organizations" in paths
    assert "/api/v1/projects" in paths
    assert "/api/v1/users/me" in paths


def test_docs_available(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200


def test_v1_stubs(client: TestClient) -> None:
    org = client.get("/api/v1/organizations")
    assert org.status_code == 200
    assert org.json()["phase"] == "phase-1"

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert projects.json()["phase"] == "phase-1"

    me = client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["phase"] == "phase-1"
