"""Admin use cases: patch/unlog, stats, reminder status/trigger, health, export."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.app.reminders import (
    event_to_shift_info,
    events_or_off_day,
    is_overnight_morning_tail,
)
from src.app.schedules import ScheduleEvent
from src.bot.replies import REMINDER_MESSAGE
from src.config import get_settings
from src.notifiers.telegram import TelegramNotifier
from src.services import medication_stats, reminder_service
from src.services.accounts import (
    get_telegram_id_for_account,
    list_authorized_account_ids,
)
from src.services.admin_audit import append_audit, read_audit
from src.services.calendar_service import CalendarService
from src.services.reminder_sends import (
    SOURCE_ADMIN,
    ReminderSend,
    list_sends_for_date,
    record_send,
)
from src.version import get_version

logger = logging.getLogger(__name__)

MAX_PATCH_DAYS = 31
DATA_DIR = Path("data")


class AdminError(Exception):
    """Domain error for admin operations (mapped to HTTP 400/409)."""


class NoPatientAccountError(AdminError):
    """No TELEGRAM_USER_IDS account is seeded."""


@dataclass
class PatchPreview:
    """Streak preview for patch or unlog."""

    account_id: int
    start_date: date
    end_date: date
    dates: list[date]
    already_taken: list[date]
    missing: list[date]
    applied: list[date]
    streak_before: int
    streak_after: int
    dry_run: bool
    note: str | None = None


@dataclass
class DayStatus:
    """Taken/missed for one calendar day."""

    day: date
    taken: bool


@dataclass
class AdminStats:
    """Adherence window including day-by-day."""

    account_id: int
    current_streak: int
    longest_streak: int
    adherence_rate: float
    days: int
    day_by_day: list[DayStatus]


@dataclass
class ReminderStatus:
    """Whether a reminder was sent today and whether the day is acknowledged."""

    account_id: int
    timezone: str
    today: date
    acknowledged: bool
    sends: list[ReminderSend]


@dataclass
class TriggerResult:
    """Result of forcing a reminder send now."""

    account_id: int
    sent: int
    already_acknowledged: bool
    sends: list[ReminderSend]


@dataclass
class AdminHealth:
    """Admin health snapshot."""

    version: str
    calendar_configured: bool
    data_dir_writable: bool


@dataclass
class AuditPage:
    """Recent audit lines."""

    entries: list[dict] = field(default_factory=list)


def get_patient_account_id() -> int:
    """
    Returns:
     int: First (typically only) authorized user-bot account id.

    Raises:
     NoPatientAccountError: When TELEGRAM_USER_IDS is empty or unseeded.
    """
    ids = list_authorized_account_ids()
    if not ids:
        raise NoPatientAccountError("No user-bot account configured")
    return ids[0]


def expand_date_range(start: date, end: date | None = None) -> list[date]:
    """
    Args:
     start(date): Inclusive start.
     end(date | None): Inclusive end; defaults to start.

    Returns:
     list[date]: Each day in the range.

    Raises:
     AdminError: Invalid range, future dates, or span above MAX_PATCH_DAYS.
    """
    end = end or start
    if end < start:
        raise AdminError("end_date must be on or after start_date")
    today = medication_stats._today_app_tz()
    if start > today or end > today:
        raise AdminError("cannot patch or unlog future dates")
    span = (end - start).days + 1
    if span > MAX_PATCH_DAYS:
        raise AdminError(f"range cannot exceed {MAX_PATCH_DAYS} days")
    return [start + timedelta(days=i) for i in range(span)]


def preview_patch(
    start: date,
    end: date | None = None,
    note: str | None = None,
) -> PatchPreview:
    """
    Args:
     start(date): Inclusive start.
     end(date | None): Inclusive end.
     note(str | None): Optional admin note (preview only).

    Returns:
     PatchPreview: Streak before/after if those dates were logged.
    """
    account_id = get_patient_account_id()
    dates = expand_date_range(start, end)
    taken = set(medication_stats.list_taken_dates(account_id, dates[0], dates[-1]))
    already = [d for d in dates if d in taken]
    missing = [d for d in dates if d not in taken]
    return PatchPreview(
        account_id=account_id,
        start_date=dates[0],
        end_date=dates[-1],
        dates=dates,
        already_taken=already,
        missing=missing,
        applied=[],
        streak_before=medication_stats.get_current_streak(account_id),
        streak_after=medication_stats.preview_current_streak(
            account_id, add_dates=dates
        ),
        dry_run=True,
        note=note,
    )


def apply_patch(
    actor_id: int,
    start: date,
    end: date | None = None,
    note: str | None = None,
) -> PatchPreview:
    """
    Args:
     actor_id(int): Admin Telegram user id (audit).
     start(date): Inclusive start.
     end(date | None): Inclusive end.
     note(str | None): Optional note stored in the audit log.

    Returns:
     PatchPreview: Dates newly logged and resulting streak.
    """
    preview = preview_patch(start, end, note=note)
    applied: list[date] = []
    for d in preview.missing:
        reminder_service.acknowledge_medication(preview.account_id, d)
        applied.append(d)
    append_audit(
        actor_id,
        "patch",
        {
            "start_date": preview.start_date.isoformat(),
            "end_date": preview.end_date.isoformat(),
            "applied": [d.isoformat() for d in applied],
            "note": note,
        },
    )
    return PatchPreview(
        account_id=preview.account_id,
        start_date=preview.start_date,
        end_date=preview.end_date,
        dates=preview.dates,
        already_taken=preview.already_taken,
        missing=[],
        applied=applied,
        streak_before=preview.streak_before,
        streak_after=medication_stats.get_current_streak(preview.account_id),
        dry_run=False,
        note=note,
    )


def preview_unlog(
    start: date,
    end: date | None = None,
    note: str | None = None,
) -> PatchPreview:
    """
    Args:
     start(date): Inclusive start.
     end(date | None): Inclusive end.
     note(str | None): Optional admin note (preview only).

    Returns:
     PatchPreview: Streak before/after if those dates were removed.
    """
    account_id = get_patient_account_id()
    dates = expand_date_range(start, end)
    taken = set(medication_stats.list_taken_dates(account_id, dates[0], dates[-1]))
    already = [d for d in dates if d in taken]
    missing = [d for d in dates if d not in taken]
    return PatchPreview(
        account_id=account_id,
        start_date=dates[0],
        end_date=dates[-1],
        dates=dates,
        already_taken=already,
        missing=missing,
        applied=[],
        streak_before=medication_stats.get_current_streak(account_id),
        streak_after=medication_stats.preview_current_streak(
            account_id, remove_dates=already
        ),
        dry_run=True,
        note=note,
    )


def apply_unlog(
    actor_id: int,
    start: date,
    end: date | None = None,
    note: str | None = None,
) -> PatchPreview:
    """
    Args:
     actor_id(int): Admin Telegram user id (audit).
     start(date): Inclusive start.
     end(date | None): Inclusive end.
     note(str | None): Optional note stored in the audit log.

    Returns:
     PatchPreview: Dates actually removed and resulting streak.
    """
    preview = preview_unlog(start, end, note=note)
    applied: list[date] = []
    for d in preview.already_taken:
        if medication_stats.remove_taken(preview.account_id, d):
            reminder_service.clear_acknowledgment(preview.account_id, d)
            applied.append(d)
    append_audit(
        actor_id,
        "unlog",
        {
            "start_date": preview.start_date.isoformat(),
            "end_date": preview.end_date.isoformat(),
            "applied": [d.isoformat() for d in applied],
            "note": note,
        },
    )
    return PatchPreview(
        account_id=preview.account_id,
        start_date=preview.start_date,
        end_date=preview.end_date,
        dates=preview.dates,
        already_taken=[],
        missing=preview.missing,
        applied=applied,
        streak_before=preview.streak_before,
        streak_after=medication_stats.get_current_streak(preview.account_id),
        dry_run=False,
        note=note,
    )


def get_admin_stats(days: int = 30) -> AdminStats:
    """
    Args:
     days(int): Window length including today (1–180).

    Returns:
     AdminStats: Streaks, rate, and day-by-day taken/missed.
    """
    account_id = get_patient_account_id()
    return AdminStats(
        account_id=account_id,
        current_streak=medication_stats.get_current_streak(account_id),
        longest_streak=medication_stats.get_longest_streak(account_id),
        adherence_rate=medication_stats.get_adherence_rate(account_id, days=days),
        days=days,
        day_by_day=[
            DayStatus(day=d, taken=taken)
            for d, taken in medication_stats.get_day_statuses(account_id, days=days)
        ],
    )


def get_reminder_status() -> ReminderStatus:
    """
    Returns:
     ReminderStatus: Sends for today in the app timezone, plus ack state.
    """
    account_id = get_patient_account_id()
    settings = get_settings()
    today = medication_stats._today_app_tz()
    return ReminderStatus(
        account_id=account_id,
        timezone=settings.timezone,
        today=today,
        acknowledged=reminder_service.is_medication_acknowledged(account_id, today),
        sends=list_sends_for_date(account_id, today),
    )


async def _today_reminder_slots(
    now: datetime | None = None,
) -> list[tuple[date, datetime]]:
    """Today's calendar (or Off) reminder times, ignoring due/slot/ack."""
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    if now is None:
        now = datetime.now(tz).replace(tzinfo=None)
    today = now.date()
    events: list[dict] = []
    if settings.is_calendar_configured:
        try:
            events = await CalendarService().get_shifts_for_date(today)
        except Exception as e:
            logger.warning("Could not fetch calendar for admin trigger: %s", e)
    events = events_or_off_day(events, today)
    slots: list[tuple[date, datetime]] = []
    for event in events:
        parsed = event_to_shift_info(event, settings.timezone)
        if not parsed:
            continue
        shift_date, shift_info = parsed
        if not shift_info.get("same_day", True) and shift_date < today:
            continue
        if is_overnight_morning_tail(shift_info):
            continue
        reminder_dt = reminder_service.get_reminder_time(shift_date, shift_info)
        if reminder_dt is None:
            continue
        slots.append((shift_date, reminder_dt))
    return slots


async def trigger_reminder_now(actor_id: int) -> TriggerResult:
    """
    Args:
     actor_id(int): Admin Telegram user id (audit).

    Returns:
     TriggerResult: How many messages were sent.

    Raises:
     AdminError: Patient has no Telegram binding.
    """
    account_id = get_patient_account_id()
    chat_id = get_telegram_id_for_account(account_id)
    if chat_id is None:
        raise AdminError("Patient account has no Telegram binding")
    today = medication_stats._today_app_tz()
    already = reminder_service.is_medication_acknowledged(account_id, today)
    slots = await _today_reminder_slots()
    if not slots:
        raise AdminError("No reminder slot for today")
    notifier = TelegramNotifier()
    sent = 0
    for shift_date, reminder_dt in slots:
        await notifier.send_medication_reminder(chat_id, REMINDER_MESSAGE)
        reminder_service.register_pending_reminder(
            account_id, shift_date, reminder_dt
        )
        record_send(
            account_id=account_id,
            shift_date=shift_date,
            reminder_dt=reminder_dt,
            source=SOURCE_ADMIN,
        )
        sent += 1
    append_audit(actor_id, "trigger", {"sent": sent})
    return TriggerResult(
        account_id=account_id,
        sent=sent,
        already_acknowledged=already,
        sends=list_sends_for_date(account_id, today),
    )


def get_admin_health() -> AdminHealth:
    """
    Returns:
     AdminHealth: Version, calendar flag, and whether data/ is writable.
    """
    writable = False
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except OSError as e:
        logger.warning("data/ is not writable: %s", e)
    return AdminHealth(
        version=get_version(),
        calendar_configured=get_settings().is_calendar_configured,
        data_dir_writable=writable,
    )


async def get_upcoming_shifts(days: int = 7) -> list[ScheduleEvent]:
    """
    Args:
     days(int): How many days ahead to list (including today).

    Returns:
     list[ScheduleEvent]: Calendar events in the window.
    """
    settings = get_settings()
    if not settings.is_calendar_configured:
        return []
    today = medication_stats._today_app_tz()
    end_date = today + timedelta(days=days)
    events = await CalendarService().get_shifts_for_range(today, end_date)
    result: list[ScheduleEvent] = []
    for event in events:
        summary = event.get("summary", "Unknown")
        start = event.get("start", {})
        if "date" in start:
            result.append(ScheduleEvent(summary=summary, date_part=start["date"]))
        else:
            date_time = start.get("dateTime", "")[:16]
            if date_time:
                result.append(
                    ScheduleEvent(
                        summary=summary,
                        date_part=date_time[:10],
                        time_part=date_time[11:16],
                    )
                )
    return result


def export_taken_csv(days: int = 30) -> str:
    """
    Args:
     days(int): Window length including today.

    Returns:
     str: CSV with date,taken columns.
    """
    account_id = get_patient_account_id()
    rows = medication_stats.get_day_statuses(account_id, days=days)
    lines = ["date,taken"]
    for d, taken in rows:
        lines.append(f"{d.isoformat()},{1 if taken else 0}")
    return "\n".join(lines) + "\n"


def get_audit(limit: int = 20) -> AuditPage:
    """
    Args:
     limit(int): Max most-recent audit lines.

    Returns:
     AuditPage: Newest first.
    """
    return AuditPage(entries=read_audit(limit=limit))
