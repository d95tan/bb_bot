"""
Export calendar events for a month and show their shift group (AM, PM, Night, Off, etc.).

Usage:
    python scripts/export_events_shift_groups.py [month] [year]

If month/year are omitted, uses the current month in the app timezone.
Example:
    python scripts/export_events_shift_groups.py 2 2025
"""

import asyncio
import calendar
import sys
from datetime import date, timedelta

# Add project root to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0].rstrip("/\\"))

from src.config import get_settings, get_shift_config
from src.services.calendar_service import CalendarService
from src.bot.reminder_job import _event_to_shift_info


def first_and_last_day_of_month(year: int, month: int) -> tuple[date, date]:
    """Return (first_day, last_day) for the given month."""
    first = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    last = date(year, month, last_day)
    return first, last


async def fetch_events_for_month(
    calendar_service: CalendarService,
    first: date,
    last: date,
) -> list[tuple[date, dict]]:
    """Fetch all events day-by-day for the date range. Returns [(date, event), ...]."""
    out: list[tuple[date, dict]] = []
    day = first
    while day <= last:
        try:
            events = await calendar_service.get_shifts_for_date(day)
            for event in events:
                out.append((day, event))
        except Exception as e:
            print(f"Warning: failed to fetch {day}: {e}", file=sys.stderr)
        day += timedelta(days=1)
    return out


def main() -> None:
    """Parse args, fetch calendar events for the month, print date/summary/time/shift_group."""
    settings = get_settings()
    tz_str = settings.timezone
    today = date.today()

    if len(sys.argv) >= 3:
        try:
            month = int(sys.argv[1])
            year = int(sys.argv[2])
            if not (1 <= month <= 12 and 2000 <= year <= 2100):
                raise ValueError("month 1-12, year 2000-2100")
        except (ValueError, IndexError):
            print(f"Usage: {sys.argv[0]} [month] [year]", file=sys.stderr)
            print(f"  e.g. {sys.argv[0]} 2 2025", file=sys.stderr)
            sys.exit(1)
    else:
        year, month = today.year, today.month

    first_day, last_day = first_and_last_day_of_month(year, month)
    month_name = calendar.month_name[month]

    if not settings.google_refresh_token:
        print("Google Calendar not configured. Set GOOGLE_REFRESH_TOKEN (run telebot-auth).", file=sys.stderr)
        sys.exit(1)

    async def run() -> None:
        """Fetch events and map each to shift group."""
        calendar_service = CalendarService()
        pairs = await fetch_events_for_month(calendar_service, first_day, last_day)
        shift_config = get_shift_config()

        rows: list[tuple[date, str, str, str]] = []
        for day, event in pairs:
            parsed = _event_to_shift_info(event, tz_str)
            if not parsed:
                continue
            shift_date, shift_info = parsed
            group = shift_config.get_shift_group(shift_info)
            summary = (event.get("summary") or "(no title)").strip()
            if shift_info.get("all_day"):
                time_str = "all day"
            else:
                time_str = f"{shift_info.get('start', '?')}–{shift_info.get('end', '?')}"
            rows.append((shift_date, summary, time_str, group))

        rows.sort(key=lambda r: (r[0], r[2]))

        print(f"Events for {month_name} {year} ({tz_str})")
        print("-" * 60)
        if not rows:
            print("(no events)")
            return
        for d, summary, time_str, group in rows:
            print(f"  {d.isoformat()}  {summary:<20}  {time_str:<18}  → {group}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
