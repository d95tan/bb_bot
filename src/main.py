"""Main entry point for the Telegram Shift Bot."""

import logging
import sys
from datetime import timedelta

from telegram.ext import Application

from src.config import get_settings
from src.bot.handlers import setup_handlers, set_bot_commands
from src.bot.reminder_job import check_and_send_reminders


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

    settings = get_settings()
    if application.job_queue and settings.is_calendar_configured:
        interval = settings.reminder_job_interval_seconds
        # first run soon, but not more than interval
        first = min(30, max(5, interval // 10))
        application.job_queue.run_repeating(
            check_and_send_reminders,
            interval=timedelta(seconds=interval),
            first=first,
        )
        logger.info(
            "Reminder job scheduled every %s seconds (first run in %s s).",
            interval,
            first,
        )
    elif application.job_queue:
        logger.debug("Calendar not configured; reminder job not started.")


def main() -> None:
    """Start the bot."""
    logger.info("Starting Shift Schedule Bot...")

    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error(
            "Please make sure you have a .env file with required configuration.")
        sys.exit(1)

    # Check calendar configuration
    if not settings.is_calendar_configured:
        logger.warning(
            "Google Calendar not configured. "
            "Run 'telebot-auth' (or python -m scripts.auth_setup) to set up authorization."
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
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
