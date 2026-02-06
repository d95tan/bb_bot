"""
Reminder job: periodically check calendar for due reminders and send Telegram messages.
Uses reminder_service for reminder time, slot acquisition, and acknowledgment state.
"""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.config import get_settings
from src.services.calendar_service import CalendarService
from src.services import reminder_service

logger = logging.getLogger(__name__)

REMINDER_MESSAGE = (
    "💊 Medication reminder\n\n"
    "Time to take your medication before/for your shift.\n\n"
    "Tap below when done, or use /took_medication"
)


def _event_to_shift_info(event: dict, tz_str: str) -> tuple[date, dict] | None:
    """
    Build (shift_date, shift_info) from a Google Calendar event for reminder logic.
    Returns None if event is all-day (no reminder).
    """
    start_data = event.get("start", {})
    end_data = event.get("end", {})

    if "date" in start_data:
        # All-day event -> no reminder
        return None

    date_time_str = start_data.get("dateTime")
    end_time_str = end_data.get("dateTime")
    if not date_time_str or not end_time_str:
        return None

    try:
        # Parse ISO datetimes (may include Z or +HH:MM)
        start_dt = datetime.fromisoformat(date_time_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

    tz = ZoneInfo(tz_str)
    if start_dt.tzinfo:
        start_dt = start_dt.astimezone(tz)
    else:
        start_dt = start_dt.replace(tzinfo=tz)
    if end_dt.tzinfo:
        end_dt = end_dt.astimezone(tz)
    else:
        end_dt = end_dt.replace(tzinfo=tz)

    shift_date = start_dt.date()
    same_day = start_dt.date() == end_dt.date()

    shift_info = {
        "start": start_dt.strftime("%H:%M"),
        "end": end_dt.strftime("%H:%M"),
        "same_day": same_day,
        "all_day": False,
    }
    return (shift_date, shift_info)


async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job callback: fetch today's calendar events, compute reminder times,
    and send a Telegram reminder to authorized users when due (and not yet acknowledged).
    """
    settings = get_settings()
    if not settings.is_calendar_configured:
        return
    if not settings.authorized_user_ids:
        return

    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz).replace(tzinfo=None)
    today = now.date()

    try:
        calendar_service = CalendarService()
        events = await calendar_service.get_shifts_for_date(today)
    except Exception as e:
        logger.warning("Reminder job: could not fetch calendar events: %s", e)
        return

    if not events:
        logger.info(
            "Reminder job: no events for today (%s %s), skipping.",
            today.isoformat(),
            settings.timezone,
        )
        return

    logger.info(
        "Reminder job: %s event(s) for %s, now=%s",
        len(events),
        today.isoformat(),
        now.strftime("%H:%M") if hasattr(now, "strftime") else now,
    )

    for event in events:
        parsed = _event_to_shift_info(event, settings.timezone)
        if not parsed:
            logger.info("Reminder job: skip event (all-day): %s", event.get("summary"))
            continue
        shift_date, shift_info = parsed

        reminder_dt = reminder_service.get_reminder_time(shift_date, shift_info)
        if reminder_dt is None:
            logger.info("Reminder job: no reminder for this shift (off group): %s", shift_info.get("start"))
            continue
        if now < reminder_dt:
            logger.info(
                "Reminder job: not yet due (reminder at %s, now %s)",
                reminder_dt.strftime("%H:%M"),
                now.strftime("%H:%M"),
            )
            continue

        for user_id in settings.authorized_user_ids:
            if reminder_service.is_medication_acknowledged(user_id):
                logger.info("Reminder job: user %s already acknowledged, skip", user_id)
                continue
            if not reminder_service.try_acquire_reminder_slot(user_id, reminder_dt):
                logger.info(
                    "Reminder job: slot already sent for user %s at %s",
                    user_id,
                    reminder_dt.strftime("%H:%M"),
                )
                continue
            try:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✓ I took it", callback_data="reminder_ack")],
                ])
                await context.bot.send_message(
                    chat_id=user_id,
                    text=REMINDER_MESSAGE,
                    reply_markup=keyboard,
                )
                logger.info("Sent medication reminder to user %s", user_id)
            except Exception as e:
                logger.warning("Failed to send reminder to user %s: %s", user_id, e)
