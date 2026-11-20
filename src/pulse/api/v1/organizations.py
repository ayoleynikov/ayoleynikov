"""Organization API stubs (Phase 1 — not implemented)."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/organizations", tags=["organizations"])


class StubResponse(BaseModel):
    detail: str
    phase: str = "phase-1"


@router.get("", response_model=StubResponse)
async def list_organizations() -> StubResponse:
    """List organizations — implemented in a later phase."""
    return StubResponse(detail="Organizations API not implemented yet")


@router.get("/{organization_id}", response_model=StubResponse)
async def get_organization(organization_id: str) -> StubResponse:
    """Get organization — implemented in a later phase."""
    return StubResponse(detail=f"Organization {organization_id} API not implemented yet")
