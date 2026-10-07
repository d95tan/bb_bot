"""Health check routes."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import HealthResponse
from src.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        calendar_configured=settings.is_calendar_configured,
    )
