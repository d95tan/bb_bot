"""Telegram bot command and message handlers (thin HTTP client)."""

from __future__ import annotations

import logging
from io import BytesIO

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot import replies
from src.bot.commands import COMMANDS
from src.clients.backend import BackendClient
from src.config import get_settings
from src.version import get_version

logger = logging.getLogger(__name__)


def is_authorized_user(user_id: int) -> bool:
    """Check if user is in the list of authorized users."""
    return user_id in get_settings().authorized_user_ids


def _backend() -> BackendClient:
    return BackendClient()


def _build_calendar_status(dry_run: bool, stats: dict) -> str:
    """Build the calendar status message based on results."""
    if dry_run:
        return replies.CALENDAR_STATUS_DRY_RUN

    created = stats.get("created", 0)
    skipped = stats.get("skipped", 0)
    updated = stats.get("updated", 0)
    failed = stats.get("failed", 0)

    if failed > 0 and created == 0 and updated == 0:
        return replies.CALENDAR_STATUS_ALL_FAILED.format(failed=failed)

    if failed > 0:
        parts = []
        if created > 0:
            parts.append(f"{created} created")
        if updated > 0:
            parts.append(f"{updated} updated")
        if skipped > 0:
            parts.append(f"{skipped} skipped")
        parts.append(f"{failed} failed")
        return replies.CALENDAR_STATUS_PARTIAL.format(parts=", ".join(parts))

    if skipped > 0 and created == 0 and updated == 0:
        return replies.CALENDAR_STATUS_ALL_SKIPPED.format(skipped=skipped)

    if skipped > 0:
        return replies.CALENDAR_STATUS_SUCCESS_SOME_SKIPPED.format(
            created=created, skipped=skipped
        )

    return replies.CALENDAR_STATUS_ALL_SUCCESS


def _format_upload_lines(lines: list[dict]) -> list[str]:
    formatted = []
    for line in lines:
        label = line.get("label", "Unknown")
        status = line.get("status", "")
        if status == "unknown":
            formatted.append(f"• {label} (unknown)")
        elif status == "dry_run":
            formatted.append(f"• {label} (🧪 dry-run)")
        elif status == "failed":
            formatted.append(f"• {label} (⚠️ failed)")
        else:
            formatted.append(f"• {label}")
    return formatted


async def _process_image_via_api(
    image_bytes: bytes,
    processing_msg,
    filename: str = "schedule.jpg",
) -> None:
    """Upload image to backend and edit the processing message with results."""
    try:
        result = await _backend().upload_schedule(image_bytes, filename=filename)
    except httpx.HTTPStatusError as e:
        detail = e.response.text
        try:
            detail = e.response.json().get("detail", detail)
        except Exception:
            pass
        if e.response.status_code == 503:
            await processing_msg.edit_text(
                replies.CALENDAR_NOT_CONFIGURED_TEXT, parse_mode="Markdown"
            )
            return
        logger.error("Backend upload error: %s", detail)
        await processing_msg.edit_text(
            replies.IMAGE_PROCESSING_ERROR.format(error=detail)
        )
        return
    except Exception as e:
        logger.error("Error processing schedule image: %s", e)
        await processing_msg.edit_text(
            replies.IMAGE_PROCESSING_ERROR.format(error=str(e))
        )
        return

    if result.get("empty"):
        await processing_msg.edit_text(replies.IMAGE_EXTRACT_FAILED)
        return

    lines = _format_upload_lines(result.get("lines") or [])
    summary = "\n".join(lines) if lines else "No shifts found"
    calendar_status = _build_calendar_status(
        bool(result.get("dry_run")), result.get("stats") or {}
    )
    await processing_msg.edit_text(
        replies.SCHEDULE_UPLOADED_TEXT.format(
            schedule_summary=summary,
            calendar_status=calendar_status,
        ),
        parse_mode="Markdown",
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    if not is_authorized_user(update.effective_user.id):
        await update.message.reply_text(replies.UNAUTHORIZED)
        return
    await update.message.reply_text(replies.START_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized_user(update.effective_user.id):
        return
    await update.message.reply_text(replies.HELP_TEXT, parse_mode="Markdown")


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized_user(update.effective_user.id):
        return
    await update.message.reply_text(
        replies.VERSION_REPLY.format(version=get_version())
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized_user(update.effective_user.id):
        return

    try:
        data = await _backend().list_schedules(weeks=4)
    except Exception as e:
        logger.error("Error fetching schedule: %s", e)
        await update.message.reply_text(
            replies.SCHEDULE_FETCH_ERROR.format(error=str(e))
        )
        return

    if not data.get("calendar_configured", True):
        await update.message.reply_text(
            replies.CALENDAR_NOT_CONFIGURED_TEXT, parse_mode="Markdown"
        )
        return

    events = data.get("events") or []
    if not events:
        await update.message.reply_text(replies.NO_SCHEDULE_FOUND)
        return

    lines = [replies.SCHEDULE_HEADER]
    for event in events:
        summary = event.get("summary", "Unknown")
        date_part = event.get("date_part", "")
        time_part = event.get("time_part")
        if time_part:
            lines.append(f"• {date_part} {time_part}: *{summary}*")
        else:
            lines.append(f"• {date_part}: *{summary}*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized_user(update.effective_user.id):
        return

    processing_msg = await update.message.reply_text(replies.PROCESSING_IMAGE_TEXT)
    try:
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        logger.info(
            "Received photo: %sx%s pixels, file_size=%s bytes",
            photo.width,
            photo.height,
            photo.file_size,
        )
        image_bytes = BytesIO()
        await photo_file.download_to_memory(image_bytes)
        image_bytes.seek(0)
        await _process_image_via_api(image_bytes.read(), processing_msg)
    except Exception as e:
        logger.error("Error processing schedule image: %s", e)
        await processing_msg.edit_text(
            replies.IMAGE_PROCESSING_ERROR.format(error=str(e))
        )


def _streak_suffix(n: int) -> str:
    return "" if n == 1 else "s"


async def took_medication_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not is_authorized_user(update.effective_user.id):
        return
    user_id = update.effective_user.id
    try:
        result = await _backend().ack_medication(user_id)
    except Exception as e:
        logger.error("Ack failed: %s", e)
        await update.message.reply_text(f"❌ Could not record medication: {e}")
        return
    streak = int(result.get("streak") or 0)
    if streak > 0:
        text = replies.TOOK_MEDICATION_REPLY_WITH_STREAK.format(streak=streak)
    else:
        text = replies.TOOK_MEDICATION_REPLY
    await update.message.reply_text(text)


async def reminder_ack_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.callback_query:
        return
    if not is_authorized_user(update.effective_user.id):
        await update.callback_query.answer(replies.NOT_AUTHORIZED_CALLBACK)
        return
    user_id = update.effective_user.id
    try:
        result = await _backend().ack_medication(user_id)
    except Exception as e:
        logger.error("Ack callback failed: %s", e)
        await update.callback_query.answer("Failed")
        return
    await update.callback_query.answer(replies.REMINDER_ACK_CALLBACK_ANSWER)
    if update.callback_query.message:
        streak = int(result.get("streak") or 0)
        if streak > 0:
            text = replies.REMINDER_ACK_EDIT_TEXT_WITH_STREAK.format(streak=streak)
        else:
            text = replies.REMINDER_ACK_EDIT_TEXT
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")


async def medication_stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not is_authorized_user(update.effective_user.id):
        return
    user_id = update.effective_user.id
    try:
        data = await _backend().medication_stats(user_id, days=30)
    except Exception as e:
        logger.error("Stats failed: %s", e)
        await update.message.reply_text(f"❌ Could not load stats: {e}")
        return

    current = int(data.get("current_streak") or 0)
    longest = int(data.get("longest_streak") or 0)
    rate = float(data.get("adherence_rate") or 0.0)
    if current == 0 and longest == 0:
        await update.message.reply_text(replies.MEDICATION_STATS_NO_DATA)
        return
    lines = [
        replies.MEDICATION_STATS_HEADER,
        replies.MEDICATION_STATS_CURRENT.format(n=current, s=_streak_suffix(current)),
        replies.MEDICATION_STATS_LONGEST.format(n=longest, s=_streak_suffix(longest)),
        replies.MEDICATION_STATS_RATE.format(pct=rate * 100),
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not is_authorized_user(update.effective_user.id):
        return
    await update.message.reply_text(replies.SEND_SCREENSHOT)


async def handle_document(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not is_authorized_user(update.effective_user.id):
        return

    document = update.message.document
    if not document.mime_type or not document.mime_type.startswith("image/"):
        await update.message.reply_text(replies.NOT_AN_IMAGE)
        return

    processing_msg = await update.message.reply_text(
        replies.PROCESSING_IMAGE_TEXT + replies.PROCESSING_IMAGE_UNCOMPRESSED_SUFFIX,
        parse_mode="Markdown",
    )
    try:
        doc_file = await context.bot.get_file(document.file_id)
        logger.info(
            "Received document: %s, mime=%s, size=%s bytes",
            document.file_name,
            document.mime_type,
            document.file_size,
        )
        image_bytes = BytesIO()
        await doc_file.download_to_memory(image_bytes)
        image_bytes.seek(0)
        await _process_image_via_api(
            image_bytes.read(),
            processing_msg,
            filename=document.file_name or "schedule.jpg",
        )
    except Exception as e:
        logger.error("Error processing schedule document: %s", e)
        await processing_msg.edit_text(
            replies.IMAGE_PROCESSING_ERROR.format(error=str(e))
        )


def setup_handlers(application: Application) -> None:
    """Register all handlers with the application."""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("version", version_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("took_medication", took_medication_command))
    application.add_handler(CommandHandler("medication_stats", medication_stats_command))
    application.add_handler(
        CallbackQueryHandler(reminder_ack_callback, pattern="^reminder_ack$")
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )


async def set_bot_commands(application: Application) -> None:
    """Set bot commands in Telegram."""
    await application.bot.set_my_commands(COMMANDS)
