"""JWT auth hooks — token mint (dev/test) and principal introspection."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from pulse.config import Settings
from pulse.models.membership import OrganizationRole
from pulse.security.audit import get_audit_recorder
from pulse.security.deps import CurrentPrincipal, get_current_principal
from pulse.security.jwt_tokens import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    """Dev/test token mint — production should use IdP exchange."""

    user_id: UUID | None = None
    email: str | None = None
    organization_id: UUID | None = None
    role: OrganizationRole = OrganizationRole.MEMBER
    is_superuser: bool = False
    scopes: list[str] = Field(default_factory=list)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
    note: str = (
        "Dev/test mint endpoint. Wire OIDC/IdP exchange before production. "
        "Never log the token value."
    )


class PrincipalResponse(BaseModel):
    user_id: UUID
    email: str | None
    organization_id: UUID | None
    role: str | None
    is_superuser: bool
    scopes: list[str]


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/token", response_model=TokenResponse)
async def mint_token(body: TokenRequest, request: Request) -> TokenResponse:
    settings = _settings(request)
    if settings.env not in {"development", "test"} and not settings.debug:
        raise HTTPException(
            status_code=403,
            detail="token mint disabled outside development/test (use IdP)",
        )
    user_id = body.user_id or uuid4()
    token = create_access_token(
        subject=user_id,
        settings=settings,
        email=str(body.email) if body.email else None,
        org_id=body.organization_id,
        role=body.role.value,
        is_superuser=body.is_superuser,
        scopes=body.scopes,
    )
    get_audit_recorder().record(
        "auth.token_minted",
        actor_user_id=user_id,
        organization_id=body.organization_id,
        details={"role": body.role.value, "is_superuser": body.is_superuser},
    )
    return TokenResponse(access_token=token, expires_minutes=settings.jwt_expire_minutes)


@router.get("/me", response_model=PrincipalResponse)
async def auth_me(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> PrincipalResponse:
    return PrincipalResponse(
        user_id=principal.user_id,
        email=principal.email,
        organization_id=principal.org_id,
        role=principal.role,
        is_superuser=principal.is_superuser,
        scopes=principal.scopes,
    )
