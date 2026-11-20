"""CORS defaults and API rate limiting."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pulse.config import Settings
from pulse.main import create_app
from pulse.security.rate_limit import ApiRateLimiter


def test_cors_absent_by_default() -> None:
    settings = Settings(env="test", jwt_secret="x" * 32, cors_allow_origins="")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        # No CORS middleware → no ACAO header reflecting evil origin
        assert response.headers.get("access-control-allow-origin") != "https://evil.example"


def test_cors_allowlist() -> None:
    settings = Settings(
        env="test",
        jwt_secret="x" * 32,
        cors_allow_origins="https://app.example",
        api_rate_limit_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "https://app.example"})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://app.example"


def test_rate_limiter_blocks() -> None:
    limiter = ApiRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert limiter.allow("a") is False


def test_rate_limit_middleware_returns_429() -> None:
    settings = Settings(
        env="test",
        jwt_secret="x" * 32,
        api_rate_limit_enabled=True,
        api_rate_limit_requests=2,
        api_rate_limit_window_seconds=60,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/organizations").status_code == 200
        assert client.get("/api/v1/organizations").status_code == 200
        third = client.get("/api/v1/organizations")
        assert third.status_code == 429
        # probes exempt
        assert client.get("/health").status_code == 200
