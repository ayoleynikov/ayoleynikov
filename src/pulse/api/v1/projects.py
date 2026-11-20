"""Project API stubs (Phase 1 — not implemented)."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/projects", tags=["projects"])


class StubResponse(BaseModel):
    detail: str
    phase: str = "phase-1"


@router.get("", response_model=StubResponse)
async def list_projects() -> StubResponse:
    """List projects — implemented in a later phase."""
    return StubResponse(detail="Projects API not implemented yet")


@router.get("/{project_id}", response_model=StubResponse)
async def get_project(project_id: str) -> StubResponse:
    """Get project — implemented in a later phase."""
    return StubResponse(detail=f"Project {project_id} API not implemented yet")
