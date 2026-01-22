"""Telegram bot command and message handlers."""

import logging
from datetime import date, timedelta
from io import BytesIO

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from src.config import get_settings
from src.services.image_processor import process_schedule_image
from src.services.calendar_service import CalendarService
from src.bot.commands import (
    COMMANDS,
    HELP_TEXT,
    START_TEXT,
    CALENDAR_NOT_CONFIGURED_TEXT,
    SCHEDULE_UPLOADED_TEXT,
    PROCESSING_IMAGE_TEXT,
)


logger = logging.getLogger(__name__)


def is_authorized_user(user_id: int) -> bool:
    """Check if user is the authorized user."""
    settings = get_settings()
    return user_id == settings.telegram_user_id


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not update.effective_user:
        return

    if not is_authorized_user(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return

    await update.message.reply_text(START_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_authorized_user(update.effective_user.id):
        return

    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /schedule command - show current schedule from Google Calendar."""
    if not is_authorized_user(update.effective_user.id):
        return

    settings = get_settings()
    if not settings.is_calendar_configured:
        await update.message.reply_text(CALENDAR_NOT_CONFIGURED_TEXT, parse_mode="Markdown")
        return

    try:
        calendar_service = CalendarService()

        # Get schedule for next 4 weeks
        today = date.today()
        end_date = today + timedelta(weeks=4)

        events = await calendar_service.get_shifts_for_range(today, end_date)

        if not events:
            await update.message.reply_text(
                "📭 No upcoming shifts found in your calendar.\n\n"
                "Upload a screenshot of your shift schedule to add shifts."
            )
            return

        # Format schedule
        lines = ["📅 *Your Upcoming Schedule:*\n"]

        for event in events:
            summary = event.get("summary", "Unknown")
            start = event.get("start", {})

            # Handle all-day vs timed events
            if "date" in start:
                event_date = start["date"]
                lines.append(f"• {event_date}: *{summary}*")
            else:
                date_time = start.get("dateTime", "")[
                    :16]  # Get YYYY-MM-DDTHH:MM
                if date_time:
                    date_part = date_time[:10]
                    time_part = date_time[11:16]
                    lines.append(f"• {date_part} {time_part}: *{summary}*")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error fetching schedule: {e}")
        await update.message.reply_text(f"❌ Error fetching schedule: {str(e)}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages (schedule screenshots)."""
    if not is_authorized_user(update.effective_user.id):
        return

    settings = get_settings()
    if not settings.is_calendar_configured:
        await update.message.reply_text(CALENDAR_NOT_CONFIGURED_TEXT, parse_mode="Markdown")
        return

    # Send processing message
    processing_msg = await update.message.reply_text(PROCESSING_IMAGE_TEXT)

    try:
        # Download the photo (get the largest size)
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)

        # Download to bytes
        image_bytes = BytesIO()
        await photo_file.download_to_memory(image_bytes)
        image_bytes.seek(0)

        # Process the image with OCR
        schedule_data = process_schedule_image(image_bytes.read())

        if not schedule_data:
            await processing_msg.edit_text(
                "❌ Could not extract schedule from the image. "
                "Please make sure the screenshot is clear and try again."
            )
            return

        # Create calendar events (or dry-run if uploads disabled)
        calendar_service = CalendarService() if settings.enable_calendar_upload else None
        dry_run = not settings.enable_calendar_upload

        if dry_run:
            logger.warning("Dry-run mode: calendar uploads disabled")
            
        created_events = []
        for entry in schedule_data:
            shift_date = entry["date"]
            shift_code = entry["shift"]
            shift_info = entry.get("shift_info")

            if shift_info:
                if dry_run:
                    # Dry-run mode: just log what would be created
                    created_events.append(
                        f"• {shift_date.strftime('%a %d %b')}: {shift_code} (🧪 dry-run)")
                    
                else:
                    try:
                        await calendar_service.create_shift_event(
                            shift_date=shift_date,
                            shift_info=shift_info
                        )
                        created_events.append(
                            f"• {shift_date.strftime('%a %d %b')}: {shift_code}")
                    except Exception as e:
                        logger.error(f"Failed to create calendar event: {e}")
                        created_events.append(
                            f"• {shift_date.strftime('%a %d %b')}: {shift_code} (⚠️ failed)")
            else:
                created_events.append(
                    f"• {shift_date.strftime('%a %d %b')}: {shift_code} (unknown)")

        logger.info("Created events:\n" + "\n".join(created_events) if created_events else "No shifts found")

        # Update message with results
        summary = "\n".join(
            created_events) if created_events else "No shifts found"
        
        if dry_run:
            calendar_status = "🧪 DRY-RUN MODE: Calendar uploads disabled"
        else:
            calendar_status = "✅ All shifts added to Google Calendar!"
        
        await processing_msg.edit_text(
            SCHEDULE_UPLOADED_TEXT.format(
                schedule_summary=summary,
                calendar_status=calendar_status
            ),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error processing schedule image: {e}")
        await processing_msg.edit_text(
            f"❌ An error occurred while processing your schedule: {str(e)}"
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    if not is_authorized_user(update.effective_user.id):
        return

    await update.message.reply_text(
        "📷 Please send me a screenshot of your shift schedule.\n\n"
        "Use /help to see available commands."
    )


def setup_handlers(application: Application) -> None:
    """Register all handlers with the application."""
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schedule", schedule_command))

    # Photo handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Text message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text_message))


async def set_bot_commands(application: Application) -> None:
    """Set bot commands in Telegram."""
    await application.bot.set_my_commands(COMMANDS)
