"""HTTP route modules."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.routers import health, medication, schedules


def build_api_router() -> APIRouter:
    """Aggregate all versionless API routers."""
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(schedules.router)
    router.include_router(medication.router)
    return router
