"""Shared pytest fixtures — no live external APIs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pulse.config import Settings
from pulse.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        debug=False,
        log_level="WARNING",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="pulse",
        postgres_password="pulse",
        postgres_db="pulse_test",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-not-for-production",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
