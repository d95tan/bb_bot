"""Telegram bot command and message handlers."""

import logging
from datetime import date, timedelta
from io import BytesIO

from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from src.config import get_settings, Settings
from src.services.image_processor import process_schedule_image
from src.services.calendar_service import CalendarService
from src.services import reminder_service
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
    """Check if user is in the list of authorized users."""
    settings = get_settings()
    return user_id in settings.authorized_user_ids


def _build_calendar_status(dry_run: bool, stats: dict) -> str:
    """Build the calendar status message based on results."""
    if dry_run:
        return "🧪 DRY-RUN MODE: Calendar uploads disabled"
    
    created = stats.get("created", 0)
    skipped = stats.get("skipped", 0)
    updated = stats.get("updated", 0)
    failed = stats.get("failed", 0)
    
    # All failed
    if failed > 0 and created == 0 and updated == 0:
        return f"❌ Failed to add shifts to calendar ({failed} failed)"
    
    # Some failed
    if failed > 0:
        parts = []
        if created > 0:
            parts.append(f"{created} created")
        if updated > 0:
            parts.append(f"{updated} updated")
        if skipped > 0:
            parts.append(f"{skipped} skipped")
        parts.append(f"{failed} failed")
        return f"⚠️ Partial success: {', '.join(parts)}"
    
    # All skipped (already exist)
    if skipped > 0 and created == 0 and updated == 0:
        return f"ℹ️ All {skipped} shifts already exist in calendar"
    
    # Success with some skipped
    if skipped > 0:
        return f"✅ Added to calendar ({created} new, {skipped} already existed)"
    
    # All success
    return "✅ All shifts added to Google Calendar!"


async def _process_schedule_data(schedule_data: list, settings: Settings, processing_msg: Message) -> None:
    """Process schedule data and create calendar events."""
    # Create calendar events (or dry-run if uploads disabled)
    dry_run = not settings.enable_calendar_upload
    calendar_service = None if dry_run else CalendarService()

    if dry_run:
        logger.warning("Dry-run mode: calendar uploads disabled")

    created_events = []
    stats = {"created": 0, "skipped": 0, "updated": 0, "failed": 0, "unknown": 0}

    # Clear existing events for the date range before uploading
    if calendar_service and schedule_data:
        # Get the date range from the schedule
        dates = [entry["date"] for entry in schedule_data]
        start_date = min(dates)
        end_date = max(dates)
        
        # Check if first shift is a rest day after a night shift
        # If so, preserve overnight events from previous day
        first_entry = schedule_data[0]
        first_shift_info = first_entry.get("shift_info", {})
        is_first_rest_after_night = (
            first_shift_info.get("description", "").endswith("(after night shift)")
        )
        
        logger.info(f"Clearing existing events for {start_date} to {end_date}")
        deleted_count = await calendar_service.clear_date_range(
            start_date=start_date,
            end_date=end_date,
            preserve_overnight_from_previous=is_first_rest_after_night,
        )
        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} existing events")

    for entry in schedule_data:
        shift_date = entry["date"]
        shift_code = entry["shift"]
        shift_info = entry.get("shift_info")

        # Build base message
        shift_name = shift_info.get("name", shift_code) if shift_info else shift_code
        base_msg = f"• {shift_date.strftime('%a %d %b')}: {shift_name}"

        if not shift_info:
            created_events.append(f"{base_msg} (unknown)")
            stats["unknown"] += 1
            continue

        if dry_run:
            created_events.append(f"{base_msg} (🧪 dry-run)")
            continue

        # Create the calendar event (no need to check for existing - we already cleared)
        try:
            await calendar_service.create_shift_event(
                shift_date=shift_date,
                shift_info=shift_info,
            )
            created_events.append(base_msg)
            stats["created"] += 1
        except Exception as e:
            logger.error(f"Failed to create calendar event: {e}")
            created_events.append(f"{base_msg} (⚠️ failed)")
            stats["failed"] += 1

    logger.info("Created events:\n" + "\n".join(created_events) if created_events else "No shifts found")

    # Update message with results
    summary = "\n".join(created_events) if created_events else "No shifts found"

    # Generate appropriate status message based on results
    calendar_status = _build_calendar_status(dry_run, stats)

    await processing_msg.edit_text(
        SCHEDULE_UPLOADED_TEXT.format(
            schedule_summary=summary,
            calendar_status=calendar_status
        ),
        parse_mode="Markdown"
    )


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
        
        # Log image dimensions (Telegram compresses photos)
        logger.info(f"Received photo: {photo.width}x{photo.height} pixels, file_size={photo.file_size} bytes")

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

        # Process the schedule data and update calendar
        await _process_schedule_data(schedule_data, settings, processing_msg)

    except Exception as e:
        logger.error(f"Error processing schedule image: {e}")
        await processing_msg.edit_text(
            f"❌ An error occurred while processing your schedule: {str(e)}"
        )


async def took_medication_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /took_medication - mark medication as acknowledged for today."""
    if not is_authorized_user(update.effective_user.id):
        return
    user_id = update.effective_user.id
    reminder_service.acknowledge_medication(user_id)
    await update.message.reply_text("✅ Recorded. Stay safe!")


async def reminder_ack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline 'I took it' button on reminder message."""
    if not update.callback_query:
        return
    if not is_authorized_user(update.effective_user.id):
        await update.callback_query.answer("Not authorized.")
        return
    user_id = update.effective_user.id
    reminder_service.acknowledge_medication(user_id)
    await update.callback_query.answer("Done!")
    if update.callback_query.message:
        await update.callback_query.edit_message_text(
            "💊 _Acknowledged._",
            parse_mode="Markdown",
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    if not is_authorized_user(update.effective_user.id):
        return

    await update.message.reply_text(
        "📷 Please send me a screenshot of your shift schedule.\n\n"
        "Use /help to see available commands."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document messages (uncompressed image files)."""
    if not is_authorized_user(update.effective_user.id):
        return

    document = update.message.document
    
    # Check if it's an image
    if not document.mime_type or not document.mime_type.startswith("image/"):
        await update.message.reply_text(
            "📄 That doesn't look like an image. Please send a PNG or JPEG screenshot."
        )
        return

    settings = get_settings()
    if not settings.is_calendar_configured:
        await update.message.reply_text(CALENDAR_NOT_CONFIGURED_TEXT, parse_mode="Markdown")
        return

    # Send processing message
    processing_msg = await update.message.reply_text(
        PROCESSING_IMAGE_TEXT + "\n_(Using uncompressed image for better accuracy)_",
        parse_mode="Markdown"
    )

    try:
        # Download the document
        doc_file = await context.bot.get_file(document.file_id)
        
        logger.info(f"Received document: {document.file_name}, mime={document.mime_type}, size={document.file_size} bytes")

        # Download to bytes
        image_bytes = BytesIO()
        await doc_file.download_to_memory(image_bytes)
        image_bytes.seek(0)

        # Process the image with OCR
        schedule_data = process_schedule_image(image_bytes.read())

        if not schedule_data:
            await processing_msg.edit_text(
                "❌ Could not extract schedule from the image. "
                "Please make sure the screenshot is clear and try again."
            )
            return

        # Reuse the same logic from handle_photo
        await _process_schedule_data(
            schedule_data, settings, processing_msg
        )

    except Exception as e:
        logger.error(f"Error processing schedule document: {e}")
        await processing_msg.edit_text(
            f"❌ An error occurred while processing your schedule: {str(e)}"
        )


def setup_handlers(application: Application) -> None:
    """Register all handlers with the application."""
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("took_medication", took_medication_command))

    # Reminder acknowledgment button
    application.add_handler(
        CallbackQueryHandler(reminder_ack_callback, pattern="^reminder_ack$")
    )

    # Photo handler (compressed by Telegram)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Document handler (uncompressed images - better quality)
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))

    # Text message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text_message))


async def set_bot_commands(application: Application) -> None:
    """Set bot commands in Telegram."""
    await application.bot.set_my_commands(COMMANDS)
