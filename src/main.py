"""Main entry point for the Telegram user-bot (thin API client)."""

import logging
import sys

from telegram.ext import Application

from src.bot.handlers import setup_handlers, set_bot_commands
from src.config import get_settings


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Initialize bot commands after startup. Reminders are owned by the API."""
    logger.info("Setting bot commands...")
    await set_bot_commands(application)
    logger.info("Bot commands set.")
    logger.info(
        "Reminders are handled by the API process (api_base_url=%s).",
        get_settings().api_base_url,
    )


def main() -> None:
    """Start the Telegram bot."""
    logger.info("Starting Shift Schedule Bot (API client)...")

    try:
        settings = get_settings()
    except Exception as e:
        logger.error("Failed to load settings: %s", e)
        logger.error(
            "Please make sure you have a .env file with required configuration."
        )
        sys.exit(1)

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    setup_handlers(application)

    logger.info("Bot is running for user IDs: %s", settings.telegram_user_ids)
    logger.info("API base URL: %s", settings.api_base_url)
    logger.info("Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
