"""JWT + RBAC scaffolding tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pulse.config import Settings
from pulse.main import create_app
from pulse.models.membership import OrganizationRole
from pulse.security.jwt_tokens import TokenError, create_access_token, decode_access_token
from pulse.security.rbac import ForbiddenError, require_role


def test_create_and_decode_token() -> None:
    settings = Settings(env="test", jwt_secret="x" * 32)
    user_id = uuid4()
    org_id = uuid4()
    token = create_access_token(
        subject=user_id,
        settings=settings,
        email="a@example.com",
        org_id=org_id,
        role=OrganizationRole.ADMIN.value,
    )
    claims = decode_access_token(token, settings=settings)
    assert claims.sub == str(user_id)
    assert claims.org_id == str(org_id)
    assert claims.role == "admin"


def test_invalid_token_raises() -> None:
    settings = Settings(env="test", jwt_secret="x" * 32)
    with pytest.raises(TokenError):
        decode_access_token("not-a-jwt", settings=settings)


def test_require_role_hierarchy() -> None:
    require_role(OrganizationRole.ADMIN, OrganizationRole.MEMBER)
    with pytest.raises(ForbiddenError):
        require_role(OrganizationRole.VIEWER, OrganizationRole.ADMIN)
    require_role(None, OrganizationRole.OWNER, is_superuser=True)


def test_auth_me_and_mint() -> None:
    settings = Settings(env="test", jwt_secret="x" * 32, api_rate_limit_enabled=False)
    app = create_app(settings)
    with TestClient(app) as client:
        minted = client.post(
            "/api/v1/auth/token",
            json={
                "email": "ops@example.com",
                "organization_id": str(uuid4()),
                "role": "admin",
            },
        )
        assert minted.status_code == 200
        token = minted.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "ops@example.com"
        assert me.json()["role"] == "admin"

        denied = client.get("/api/v1/users/me")
        assert denied.status_code == 401
