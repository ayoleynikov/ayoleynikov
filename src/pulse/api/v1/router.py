"""Aggregate /api/v1 router tree."""

from fastapi import APIRouter

from pulse.api.v1 import auth, connectors, organizations, projects, security_ops, usage, users, workers

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(users.router)
api_router.include_router(connectors.router)
api_router.include_router(workers.router)
api_router.include_router(usage.router)
api_router.include_router(security_ops.router)
