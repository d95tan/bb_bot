"""Main entry point for the Telegram Shift Bot."""

import logging
import sys

from telegram.ext import Application

from src.config import get_settings
from src.bot.handlers import setup_handlers, set_bot_commands


# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Initialize services after bot startup."""
    logger.info("Setting bot commands...")
    await set_bot_commands(application)
    logger.info("Bot commands set.")


def main() -> None:
    """Start the bot."""
    logger.info("Starting Shift Schedule Bot...")
    
    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please make sure you have a .env file with required configuration.")
        sys.exit(1)
    
    # Check calendar configuration
    if not settings.is_calendar_configured:
        logger.warning(
            "Google Calendar not configured. "
            "Run 'python -m src.auth_setup' to set up authorization."
        )
    
    # Create application
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    
    # Setup handlers
    setup_handlers(application)
    
    # Run the bot
    logger.info(f"Bot is running for user IDs: {settings.telegram_user_ids}")
    logger.info("Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
