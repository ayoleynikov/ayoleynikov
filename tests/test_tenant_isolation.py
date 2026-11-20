"""Tenant isolation — cross-org access denied."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pulse.config import Settings
from pulse.main import create_app
from pulse.models.membership import OrganizationRole
from pulse.security.jwt_tokens import create_access_token
from pulse.security.rbac import ForbiddenError
from pulse.security.tenant import MembershipRecord, TenantContext, reset_tenant_context


def test_cross_org_membership_denied() -> None:
    user = uuid4()
    org_a = uuid4()
    org_b = uuid4()
    ctx = TenantContext(
        memberships=[
            MembershipRecord(user_id=user, organization_id=org_a, role=OrganizationRole.ADMIN)
        ]
    )
    ctx.assert_org_access(user_id=user, organization_id=org_a, minimum_role=OrganizationRole.VIEWER)
    with pytest.raises(ForbiddenError, match="not a member"):
        ctx.assert_org_access(user_id=user, organization_id=org_b)


def test_project_wrong_org_denied() -> None:
    user = uuid4()
    org_a = uuid4()
    org_b = uuid4()
    project = uuid4()
    ctx = TenantContext(
        memberships=[
            MembershipRecord(user_id=user, organization_id=org_a, role=OrganizationRole.MEMBER)
        ]
    )
    with pytest.raises(ForbiddenError, match="cross-tenant"):
        ctx.assert_project_access(
            user_id=user,
            organization_id=org_a,
            project_id=project,
            project_org_id=org_b,
        )


def test_api_tenant_check_cross_org() -> None:
    settings = Settings(env="test", jwt_secret="x" * 32, api_rate_limit_enabled=False)
    user = uuid4()
    org_a = uuid4()
    org_b = uuid4()
    reset_tenant_context(
        [
            MembershipRecord(
                user_id=user, organization_id=org_a, role=OrganizationRole.MEMBER
            )
        ]
    )
    token = create_access_token(
        subject=user,
        settings=settings,
        org_id=org_a,
        role=OrganizationRole.MEMBER.value,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        ok = client.post(
            "/api/v1/tenant/check",
            headers={"Authorization": f"Bearer {token}"},
            json={"organization_id": str(org_a)},
        )
        assert ok.status_code == 200
        assert ok.json()["allowed"] is True

        denied = client.post(
            "/api/v1/tenant/check",
            headers={"Authorization": f"Bearer {token}"},
            json={"organization_id": str(org_b)},
        )
        assert denied.status_code == 200
        assert denied.json()["allowed"] is False
        assert "not a member" in (denied.json()["detail"] or "")
