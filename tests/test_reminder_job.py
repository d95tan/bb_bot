"""Unit tests for reminder job (night-shift spanning two days, due-today logic)."""

from datetime import date, datetime, time

from src.bot.reminder_job import (
    _event_to_shift_info,
    _events_or_off_day,
    _is_overnight_morning_tail,
    _should_consider_reminder_for_today,
)
from src.services import reminder_service


class TestShouldConsiderReminderForToday:
    """
    When the job runs, we only send if reminder_dt.date() == today and now >= reminder_dt.
    This avoids sending a duplicate reminder for night shifts that span two days
    (e.g. Mon 21:00–Tue 08:00): the event overlaps Tuesday so it appears when we
    fetch Tuesday's events, but reminder_dt is Mon 20:00 → we skip on Tuesday.
    """

    def test_none_reminder_dt_returns_false(self) -> None:
        today = date(2025, 6, 15)
        now = datetime(2025, 6, 15, 20, 0)
        assert _should_consider_reminder_for_today(None, today, now) is False

    def test_reminder_on_previous_day_returns_false(self) -> None:
        """Overnight shift: reminder was Mon 20:00; today is Tue → do not send (no duplicate)."""
        reminder_dt = datetime(2025, 6, 16, 20, 0)  # Monday 20:00
        today = date(2025, 6, 17)  # Tuesday
        now = datetime(2025, 6, 17, 9, 0)  # Tuesday 09:00
        assert _should_consider_reminder_for_today(reminder_dt, today, now) is False

    def test_reminder_on_today_not_yet_due_returns_false(self) -> None:
        reminder_dt = datetime(2025, 6, 15, 20, 0)
        today = date(2025, 6, 15)
        now = datetime(2025, 6, 15, 19, 0)
        assert _should_consider_reminder_for_today(reminder_dt, today, now) is False

    def test_reminder_on_today_and_due_returns_true(self) -> None:
        reminder_dt = datetime(2025, 6, 15, 20, 0)
        today = date(2025, 6, 15)
        now = datetime(2025, 6, 15, 20, 5)
        assert _should_consider_reminder_for_today(reminder_dt, today, now) is True

    def test_reminder_on_future_day_returns_false(self) -> None:
        reminder_dt = datetime(2025, 6, 17, 9, 30)
        today = date(2025, 6, 15)
        now = datetime(2025, 6, 15, 10, 0)
        assert _should_consider_reminder_for_today(reminder_dt, today, now) is False


class TestIsOvernightMorningTail:
    """Morning segments after midnight must not trigger a second reminder."""

    def test_00_00_to_08_00_is_tail(self) -> None:
        assert _is_overnight_morning_tail({"start": "00:00", "end": "08:00", "all_day": False}) is True

    def test_07_30_to_15_30_is_real_am_shift(self) -> None:
        assert _is_overnight_morning_tail({
            "start": "07:30", "end": "15:30", "all_day": False
        }) is False

    def test_off_after_night_08_00_to_17_00_not_tail(self) -> None:
        assert _is_overnight_morning_tail({
            "start": "08:00", "end": "17:00", "all_day": False
        }) is False

    def test_all_day_not_tail(self) -> None:
        assert _is_overnight_morning_tail({"all_day": True}) is False


class TestOvernightEventParsing:
    """Overnight shift (21:00–08:00 next day): shift_date is start date so reminder is on that date."""

    def test_overnight_shift_date_is_start_date(self) -> None:
        """Reminder time is computed from shift_date; for overnight that is the start date."""
        event = {
            "start": {"dateTime": "2025-06-16T21:00:00+08:00"},
            "end": {"dateTime": "2025-06-17T08:00:00+08:00"},
        }
        result = _event_to_shift_info(event, "Asia/Singapore")
        assert result is not None
        shift_date, shift_info = result
        assert shift_date == date(2025, 6, 16)
        assert shift_info["start"] == "21:00"
        assert shift_info["end"] == "08:00"
        assert shift_info["same_day"] is False
        # So get_reminder_time(shift_date, shift_info) will be 2025-06-16 20:00 (Night -60 min).
        # When job runs on 2025-06-17, reminder_dt.date() != today → skipped.


class TestEventsOrOffDay:
    """Empty calendar days are treated as an all-day Off shift."""

    def test_empty_list_returns_synthetic_off(self) -> None:
        today = date(2025, 6, 15)
        events = _events_or_off_day([], today)
        assert events == [{"start": {"date": "2025-06-15"}, "summary": "Off"}]
        parsed = _event_to_shift_info(events[0], "Asia/Singapore")
        assert parsed is not None
        shift_date, shift_info = parsed
        assert shift_date == today
        assert shift_info["all_day"] is True
        assert shift_info["summary"] == "Off"

    def test_non_empty_list_passed_through(self) -> None:
        today = date(2025, 6, 15)
        original = [
            {
                "start": {"dateTime": "2025-06-15T07:30:00+08:00"},
                "end": {"dateTime": "2025-06-15T15:30:00+08:00"},
                "summary": "AM",
            }
        ]
        assert _events_or_off_day(original, today) is original

    def test_synthetic_off_uses_off_day_reminder_at(self) -> None:
        today = date(2025, 6, 15)
        events = _events_or_off_day([], today)
        parsed = _event_to_shift_info(events[0], "Asia/Singapore")
        assert parsed is not None
        shift_date, shift_info = parsed
        result = reminder_service.get_reminder_time(shift_date, shift_info)
        assert result is not None
        assert result.date() == today
        assert result.time() == time(9, 30)
