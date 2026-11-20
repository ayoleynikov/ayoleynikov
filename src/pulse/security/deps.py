"""FastAPI auth dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pulse.config import Settings, get_settings
from pulse.models.membership import OrganizationRole
from pulse.security.jwt_tokens import TokenClaims, TokenError, decode_access_token
from pulse.security.rbac import ForbiddenError, require_role

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentPrincipal:
    user_id: UUID
    email: str | None
    org_id: UUID | None
    role: str | None
    is_superuser: bool
    scopes: list[str]
    claims: TokenClaims


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


async def get_current_principal(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_pulse_token: Annotated[str | None, Header(alias="X-Pulse-Token")] = None,
) -> CurrentPrincipal:
    settings = _settings(request)
    token = None
    if creds and creds.scheme.lower() == "bearer":
        token = creds.credentials
    elif x_pulse_token:
        token = x_pulse_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(token, settings=settings)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        user_id = UUID(claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid subject") from exc
    org_id = UUID(claims.org_id) if claims.org_id else None
    return CurrentPrincipal(
        user_id=user_id,
        email=claims.email,
        org_id=org_id,
        role=claims.role,
        is_superuser=claims.is_superuser,
        scopes=list(claims.scopes),
        claims=claims,
    )


def require_org_role(minimum: OrganizationRole):
    """Dependency factory: require JWT role >= minimum for claim org_id."""

    async def _dep(principal: Annotated[CurrentPrincipal, Depends(get_current_principal)]) -> CurrentPrincipal:
        if principal.org_id is None and not principal.is_superuser:
            raise HTTPException(status_code=403, detail="token missing org_id claim")
        try:
            require_role(principal.role, minimum, is_superuser=principal.is_superuser)
        except ForbiddenError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return principal

    return _dep
