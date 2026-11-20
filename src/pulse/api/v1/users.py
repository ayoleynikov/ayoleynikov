"""User API — /me delegates to JWT principal when authenticated."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from pulse.security.deps import CurrentPrincipal, get_current_principal

router = APIRouter(prefix="/users", tags=["users"])


class MeResponse(BaseModel):
    user_id: UUID
    email: str | None
    organization_id: UUID | None
    role: str | None
    is_superuser: bool
    phase: str = "phase-9"


@router.get("/me", response_model=MeResponse)
async def get_current_user(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> MeResponse:
    """Current authenticated user from JWT."""
    return MeResponse(
        user_id=principal.user_id,
        email=principal.email,
        organization_id=principal.org_id,
        role=principal.role,
        is_superuser=principal.is_superuser,
    )
