"""User API stubs (Phase 1 — not implemented)."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])


class StubResponse(BaseModel):
    detail: str
    phase: str = "phase-1"


@router.get("/me", response_model=StubResponse)
async def get_current_user() -> StubResponse:
    """Current user — implemented in a later phase."""
    return StubResponse(detail="Users API not implemented yet")
