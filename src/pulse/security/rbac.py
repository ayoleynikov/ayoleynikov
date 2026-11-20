"""RBAC helpers for organization roles."""

from __future__ import annotations

from pulse.models.membership import OrganizationRole

# Higher index = more privileged.
_ROLE_RANK: dict[OrganizationRole, int] = {
    OrganizationRole.VIEWER: 1,
    OrganizationRole.MEMBER: 2,
    OrganizationRole.ADMIN: 3,
    OrganizationRole.OWNER: 4,
}


class ForbiddenError(Exception):
    """Caller lacks required role/permission."""


def parse_role(value: str | OrganizationRole | None) -> OrganizationRole | None:
    if value is None:
        return None
    if isinstance(value, OrganizationRole):
        return value
    try:
        return OrganizationRole(value)
    except ValueError as exc:
        raise ForbiddenError(f"unknown role: {value}") from exc


def role_at_least(actual: OrganizationRole | str | None, minimum: OrganizationRole) -> bool:
    role = parse_role(actual)
    if role is None:
        return False
    return _ROLE_RANK[role] >= _ROLE_RANK[minimum]


def require_role(
    actual: OrganizationRole | str | None,
    minimum: OrganizationRole,
    *,
    is_superuser: bool = False,
) -> None:
    if is_superuser:
        return
    if not role_at_least(actual, minimum):
        raise ForbiddenError(
            f"requires role {minimum.value} or higher; have {actual!r}"
        )


# Permission matrix used by API scaffolding.
PERMISSIONS: dict[str, OrganizationRole] = {
    "org:read": OrganizationRole.VIEWER,
    "org:write": OrganizationRole.ADMIN,
    "project:read": OrganizationRole.VIEWER,
    "project:write": OrganizationRole.MEMBER,
    "credentials:read": OrganizationRole.ADMIN,
    "credentials:write": OrganizationRole.ADMIN,
    "deletion:request": OrganizationRole.ADMIN,
    "usage:read": OrganizationRole.VIEWER,
    "audit:read": OrganizationRole.ADMIN,
}
