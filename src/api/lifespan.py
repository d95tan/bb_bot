"""API lifespan: account seeding + reminder worker."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.worker import reminder_worker
from src.services.accounts import seed_authorized_accounts
from src.version import get_version

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_authorized_accounts()
    stop_event = asyncio.Event()
    task = asyncio.create_task(reminder_worker(stop_event))
    app.state.reminder_stop = stop_event
    app.state.reminder_task = task
    logger.info("API started (version=%s)", get_version())
    try:
        yield
    finally:
        stop_event.set()
        await task
