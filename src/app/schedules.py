"""Schedule upload and listing use cases."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.config import get_settings
from src.services.calendar_service import CalendarService
from src.services.image_processor import process_schedule_image

logger = logging.getLogger(__name__)


@dataclass
class ScheduleLine:
    """One day from an uploaded schedule after processing."""

    shift_date: date
    label: str
    status: str  # created | failed | unknown | dry_run


@dataclass
class UploadResult:
    """Result of OCR + calendar upload."""

    lines: list[ScheduleLine] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    dry_run: bool = False
    empty: bool = False


@dataclass
class ScheduleEvent:
    """Upcoming calendar shift for display."""

    summary: str
    date_part: str
    time_part: str | None = None


async def upload_schedule_image(image_bytes: bytes) -> UploadResult:
    """OCR a schedule screenshot and sync events to Google Calendar."""
    schedule_data = process_schedule_image(image_bytes)
    if not schedule_data:
        return UploadResult(empty=True)

    settings = get_settings()
    dry_run = not settings.enable_calendar_upload
    calendar_service = None if dry_run else CalendarService()

    if dry_run:
        logger.warning("Dry-run mode: calendar uploads disabled")

    lines: list[ScheduleLine] = []
    stats = {"created": 0, "skipped": 0, "updated": 0, "failed": 0, "unknown": 0}

    if calendar_service and schedule_data:
        dates = [entry["date"] for entry in schedule_data]
        start_date = min(dates)
        end_date = max(dates)

        first_entry = schedule_data[0]
        first_shift_info = first_entry.get("shift_info", {})
        is_first_rest_after_night = (
            first_shift_info.get("description", "").endswith("(after night shift)")
        )

        logger.info("Clearing existing events for %s to %s", start_date, end_date)
        deleted_count = await calendar_service.clear_date_range(
            start_date=start_date,
            end_date=end_date,
            preserve_overnight_from_previous=is_first_rest_after_night,
        )
        if deleted_count > 0:
            logger.info("Cleared %s existing events", deleted_count)

    for entry in schedule_data:
        shift_date = entry["date"]
        shift_code = entry["shift"]
        shift_info = entry.get("shift_info")
        shift_name = shift_info.get("name", shift_code) if shift_info else shift_code
        label = f"{shift_date.strftime('%a %d %b')}: {shift_name}"

        if not shift_info:
            lines.append(ScheduleLine(shift_date, label, "unknown"))
            stats["unknown"] += 1
            continue

        if dry_run:
            lines.append(ScheduleLine(shift_date, label, "dry_run"))
            continue

        try:
            await calendar_service.create_shift_event(
                shift_date=shift_date,
                shift_info=shift_info,
            )
            lines.append(ScheduleLine(shift_date, label, "created"))
            stats["created"] += 1
        except Exception as e:
            logger.error("Failed to create calendar event: %s", e)
            lines.append(ScheduleLine(shift_date, label, "failed"))
            stats["failed"] += 1

    return UploadResult(lines=lines, stats=stats, dry_run=dry_run)


async def get_upcoming_schedule(
    weeks: int = 4,
) -> list[ScheduleEvent]:
    """Fetch upcoming shifts from Google Calendar."""
    calendar_service = CalendarService()
    today = date.today()
    end_date = today + timedelta(weeks=weeks)
    events = await calendar_service.get_shifts_for_range(today, end_date)

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
