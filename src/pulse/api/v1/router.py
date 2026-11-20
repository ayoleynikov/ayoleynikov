"""Aggregate /api/v1 router tree (stubs for later phases)."""

from fastapi import APIRouter

from pulse.api.v1 import organizations, projects, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(users.router)
