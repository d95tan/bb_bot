"""FastAPI application factory."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI

from src.api.lifespan import lifespan
from src.api.routers import build_api_router
from src.version import get_version

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)


def create_app() -> FastAPI:
    """Build the FastAPI app with routers and lifespan hooks."""
    application = FastAPI(
        title="bb_bot API",
        version=get_version(),
        lifespan=lifespan,
    )
    application.include_router(build_api_router())
    return application


app = create_app()
