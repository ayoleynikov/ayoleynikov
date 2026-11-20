"""Tenant isolation — deny cross-organization access."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pulse.models.membership import OrganizationRole
from pulse.security.rbac import ForbiddenError, require_role


@dataclass(frozen=True)
class MembershipRecord:
    user_id: UUID
    organization_id: UUID
    role: OrganizationRole
    project_ids: frozenset[UUID] = frozenset()


@dataclass
class TenantContext:
    """In-process membership index for API/tests (Postgres is source of truth in prod)."""

    memberships: list[MembershipRecord]

    def membership_for(self, user_id: UUID, organization_id: UUID) -> MembershipRecord | None:
        for m in self.memberships:
            if m.user_id == user_id and m.organization_id == organization_id:
                return m
        return None

    def assert_org_access(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        minimum_role: OrganizationRole = OrganizationRole.VIEWER,
        is_superuser: bool = False,
    ) -> MembershipRecord:
        if is_superuser:
            return MembershipRecord(
                user_id=user_id,
                organization_id=organization_id,
                role=OrganizationRole.OWNER,
            )
        membership = self.membership_for(user_id, organization_id)
        if membership is None:
            raise ForbiddenError(
                f"user {user_id} is not a member of organization {organization_id}"
            )
        require_role(membership.role, minimum_role, is_superuser=False)
        return membership

    def assert_project_access(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        minimum_role: OrganizationRole = OrganizationRole.VIEWER,
        is_superuser: bool = False,
        project_org_id: UUID | None = None,
    ) -> MembershipRecord:
        """Deny access when the project belongs to another org or user lacks membership."""
        if project_org_id is not None and project_org_id != organization_id:
            raise ForbiddenError(
                "project does not belong to the requested organization "
                "(cross-tenant access denied)"
            )
        membership = self.assert_org_access(
            user_id=user_id,
            organization_id=organization_id,
            minimum_role=minimum_role,
            is_superuser=is_superuser,
        )
        if (
            not is_superuser
            and membership.project_ids
            and project_id not in membership.project_ids
        ):
            # Optional project allow-list — empty means all org projects.
            raise ForbiddenError(
                f"user {user_id} cannot access project {project_id} in org {organization_id}"
            )
        return membership


_TENANT_CTX: TenantContext | None = None


def get_tenant_context() -> TenantContext:
    global _TENANT_CTX
    if _TENANT_CTX is None:
        _TENANT_CTX = TenantContext(memberships=[])
    return _TENANT_CTX


def reset_tenant_context(memberships: list[MembershipRecord] | None = None) -> TenantContext:
    global _TENANT_CTX
    _TENANT_CTX = TenantContext(memberships=list(memberships or []))
    return _TENANT_CTX
