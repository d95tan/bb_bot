"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require X-API-Key matching configured api_key."""
    expected = get_settings().api_key
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
