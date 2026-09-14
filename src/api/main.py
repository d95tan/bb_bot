"""API process entrypoint (`python -m src.api.main` / `telebot-api`)."""

from __future__ import annotations

import logging
import sys

from src.api.app import app  # noqa: F401 — uvicorn target: src.api.main:app
from src.config import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the API with uvicorn."""
    import uvicorn

    try:
        get_settings()
    except Exception as e:
        logger.error("Failed to load settings: %s", e)
        sys.exit(1)

    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
