"""
Due-reminder discovery use case.

Channel-agnostic: returns which accounts need a reminder; callers/notifiers send.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config import get_settings
from src.services import reminder_service
from src.services.accounts import list_authorized_account_ids, get_telegram_id_for_account
from src.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)


@dataclass
class DueReminder:
    """A reminder that should be sent now."""

    account_id: int
    telegram_chat_id: int | None
    shift_date: date
    reminder_dt: datetime


def event_to_shift_info(event: dict, tz_str: str) -> tuple[date, dict] | None:
    """
    Build (shift_date, shift_info) from a Google Calendar event for reminder logic.
    Returns None if the event cannot be used for reminders.
    """
    start_data = event.get("start", {})
    end_data = event.get("end", {})

    if "date" in start_data:
        try:
            shift_date = date.fromisoformat(start_data["date"])
        except (ValueError, TypeError):
            return None
        summary = (event.get("summary") or "").strip()
        return (shift_date, {"all_day": True, "summary": summary or None})

    date_time_str = start_data.get("dateTime")
    end_time_str = end_data.get("dateTime")
    if not date_time_str or not end_time_str:
        return None

    try:
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

    summary = (event.get("summary") or "").strip()
    shift_info = {
        "start": start_dt.strftime("%H:%M"),
        "end": end_dt.strftime("%H:%M"),
        "same_day": same_day,
        "all_day": False,
        "summary": summary or None,
    }
    return (shift_date, shift_info)


def is_overnight_morning_tail(shift_info: dict) -> bool:
    """
    True for timed blocks like 00:00–08:00 that finish an overnight shift.
    These must not get a separate AM-style reminder after midnight.
    """
    if shift_info.get("all_day"):
        return False
    start_str = shift_info.get("start", "")
    end_str = shift_info.get("end", "")
    try:
        start_parts = start_str.split(":")
        end_parts = end_str.split(":")
        sh = int(start_parts[0]) if start_parts else 0
        eh = int(end_parts[0]) if end_parts else 0
        em = int(end_parts[1]) if len(end_parts) > 1 else 0
    except (ValueError, IndexError):
        return False
    if sh >= 12:
        return False
    end_minutes = eh * 60 + em
    return end_minutes <= 9 * 60


def should_consider_reminder_for_today(
    reminder_dt: datetime | None, today: date, now: datetime
) -> bool:
    """True if reminder is on today and already due."""
    if reminder_dt is None:
        return False
    if reminder_dt.date() != today:
        return False
    if now < reminder_dt:
        return False
    return True


async def find_due_reminders(
    now: datetime | None = None,
) -> list[DueReminder]:
    """
    Fetch today's calendar events and return reminders that should be sent.

    Acquires send slots and registers pending reminders for each due item so
    callers that successfully notify do not double-send. If send fails, the
    slot TTL still prevents immediate spam (same as previous bot job behavior).
    """
    settings = get_settings()
    if not settings.is_calendar_configured:
        return []

    account_ids = list_authorized_account_ids()
    if not account_ids:
        return []

    tz = ZoneInfo(settings.timezone)
    if now is None:
        now = datetime.now(tz).replace(tzinfo=None)
    today = now.date()

    try:
        calendar_service = CalendarService()
        events = await calendar_service.get_shifts_for_date(today)
    except Exception as e:
        logger.warning("Could not fetch calendar events for reminders: %s", e)
        return []

    if not events:
        logger.info(
            "No events for today (%s %s), skipping reminders.",
            today.isoformat(),
            settings.timezone,
        )
        return []

    logger.info(
        "%s event(s) for %s, now=%s",
        len(events),
        today.isoformat(),
        now.strftime("%H:%M"),
    )

    due: list[DueReminder] = []

    for event in events:
        parsed = event_to_shift_info(event, settings.timezone)
        if not parsed:
            logger.info("Skip event (unusable): %s", event.get("summary"))
            continue
        shift_date, shift_info = parsed

        if not shift_info.get("same_day", True) and shift_date < today:
            logger.info(
                "Overnight shift started %s (before today), skip",
                shift_date.isoformat(),
            )
            continue
        if is_overnight_morning_tail(shift_info):
            logger.info(
                "Morning tail of overnight shift (%s–%s), skip",
                shift_info.get("start"),
                shift_info.get("end"),
            )
            continue

        reminder_dt = reminder_service.get_reminder_time(shift_date, shift_info)
        if not should_consider_reminder_for_today(reminder_dt, today, now):
            if reminder_dt is not None and reminder_dt.date() != today:
                logger.info(
                    "Reminder date %s is not today (%s), skip",
                    reminder_dt.date().isoformat(),
                    today.isoformat(),
                )
            elif reminder_dt is not None and now < reminder_dt:
                logger.info(
                    "Not yet due (reminder at %s, now %s)",
                    reminder_dt.strftime("%H:%M"),
                    now.strftime("%H:%M"),
                )
            continue

        for account_id in account_ids:
            if reminder_service.is_medication_acknowledged(account_id, shift_date):
                logger.info(
                    "Account %s already acknowledged for shift %s, skip",
                    account_id,
                    shift_date.isoformat(),
                )
                continue
            if not reminder_service.try_acquire_reminder_slot(account_id, reminder_dt):
                logger.info(
                    "Slot already sent for account %s at %s",
                    account_id,
                    reminder_dt.strftime("%H:%M"),
                )
                continue

            reminder_service.register_pending_reminder(
                account_id, shift_date, reminder_dt
            )
            due.append(
                DueReminder(
                    account_id=account_id,
                    telegram_chat_id=get_telegram_id_for_account(account_id),
                    shift_date=shift_date,
                    reminder_dt=reminder_dt,
                )
            )

    return due
