"""Entrypoint for the Telegram admin bot (thin API client)."""

import logging
import sys
import time

from telegram.ext import Application

from src.admin_bot.handlers import set_bot_commands, setup_handlers
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
    """Set the admin command menu after startup."""
    logger.info("Setting admin bot commands...")
    await set_bot_commands(application)
    logger.info("Admin bot commands set.")


def main() -> None:
    """Start the admin Telegram bot."""
    logger.info("Starting bb_bot admin client...")

    try:
        settings = get_settings()
    except Exception as e:
        logger.error("Failed to load settings: %s", e)
        logger.error(
            "Please make sure you have a .env file with required configuration."
        )
        sys.exit(1)

    if not settings.admin_telegram_bot_token or not settings.authorized_admin_user_ids:
        logger.warning(
            "Admin bot idle: set ADMIN_TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_USER_IDS."
        )
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    application = (
        Application.builder()
        .token(settings.admin_telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    setup_handlers(application)

    logger.info(
        "Admin bot is running for user IDs: %s",
        settings.admin_telegram_user_ids,
    )
    logger.info("API base URL: %s", settings.api_base_url)
    logger.info("Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
