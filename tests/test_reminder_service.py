"""Unit tests for reminder service and reminder job helpers."""

from datetime import date, datetime, time
from unittest.mock import MagicMock, patch

from src.services import reminder_service
from src.bot.reminder_job import _event_to_shift_info


class TestGetShiftGroup:
    """Tests for get_shift_group classification."""

    def test_all_day_is_off(self) -> None:
        assert reminder_service.get_shift_group({"all_day": True}) == "Off"

    def test_am_by_start_time(self) -> None:
        # Before 12:00
        assert reminder_service.get_shift_group({"start": "07:30", "all_day": False}) == "AM"
        assert reminder_service.get_shift_group({"start": "09:00", "all_day": False}) == "AM"

    def test_pm_by_start_time(self) -> None:
        # 12:00 up to (but not including) 19:00
        assert reminder_service.get_shift_group({"start": "13:30", "all_day": False}) == "PM"
        assert reminder_service.get_shift_group({"start": "12:00", "all_day": False}) == "PM"
        assert reminder_service.get_shift_group({"start": "18:30", "all_day": False}) == "PM"

    def test_night_by_start_time(self) -> None:
        # 19:00 onwards
        assert reminder_service.get_shift_group({"start": "21:00", "all_day": False}) == "Night"
        assert reminder_service.get_shift_group({"start": "19:00", "all_day": False}) == "Night"

    def test_08_00_08_00_classified_by_start_time(self) -> None:
        # Timed 08:00–08:00 has no special case; classified by start time → AM (before 12:00)
        assert reminder_service.get_shift_group({
            "start": "08:00", "end": "08:00", "all_day": False
        }) == "AM"

    def test_08_00_17_00_stays_am(self) -> None:
        # Project / real shift 08:00–17:00 stays am, not off
        assert reminder_service.get_shift_group({
            "start": "08:00", "end": "17:00", "all_day": False
        }) == "AM"

    def test_summary_off_uses_name_even_timed(self) -> None:
        # Event named "Off" (e.g. off-after-night 08:00–17:00) → off by name, not by time
        assert reminder_service.get_shift_group({
            "start": "08:00", "end": "17:00", "all_day": False, "summary": "Off"
        }) == "Off"

    def test_summary_nig_is_night(self) -> None:
        assert reminder_service.get_shift_group({
            "start": "21:00", "end": "08:00", "same_day": False, "all_day": False, "summary": "Nig"
        }) == "Night"

    def test_unknown_summary_falls_back_to_time(self) -> None:
        # Renamed or manual event → time-based
        assert reminder_service.get_shift_group({
            "start": "08:00", "end": "17:00", "all_day": False, "summary": "My custom shift"
        }) == "AM"


class TestGetReminderOffsetMinutes:
    """Tests for get_reminder_offset_minutes (from config)."""

    def test_am_offset(self) -> None:
        assert reminder_service.get_reminder_offset_minutes({"start": "07:30", "all_day": False}) == 30

    def test_pm_offset(self) -> None:
        assert reminder_service.get_reminder_offset_minutes({"start": "13:30", "all_day": False}) == -60

    def test_night_offset(self) -> None:
        assert reminder_service.get_reminder_offset_minutes({"start": "21:00", "all_day": False}) == -60

    def test_off_has_no_offset(self) -> None:
        assert reminder_service.get_reminder_offset_minutes({"all_day": True}) is None


class TestGetReminderTime:
    """Tests for get_reminder_time (shift_date + shift_info -> datetime or None)."""

    def test_all_day_uses_reminder_at(self) -> None:
        # Off day: reminder time from group's get_reminder_at or get_off_day_reminder_at() (fixed HH:MM)
        shift_date = date(2025, 6, 15)
        mock_config = MagicMock()
        mock_config.get_reminder_at.return_value = None  # so fallback is used
        mock_config.get_off_day_reminder_at.return_value = "09:30"
        with patch.object(reminder_service, "get_shift_config", return_value=mock_config):
            result = reminder_service.get_reminder_time(shift_date, {"all_day": True})
        assert result is not None
        assert result.date() == shift_date
        assert result.time() == time(9, 30)

    def test_timed_am_offset_after_start(self) -> None:
        # AM: 07:30 + 30 min = 08:00
        shift_date = date(2025, 6, 15)
        result = reminder_service.get_reminder_time(
            shift_date, {"start": "07:30", "end": "15:30", "all_day": False}
        )
        assert result is not None
        assert result == datetime(2025, 6, 15, 8, 0)

    def test_timed_pm_offset_before_start(self) -> None:
        # PM: 13:30 - 60 min = 12:30
        shift_date = date(2025, 6, 15)
        result = reminder_service.get_reminder_time(
            shift_date, {"start": "13:30", "end": "21:30", "all_day": False}
        )
        assert result is not None
        assert result == datetime(2025, 6, 15, 12, 30)

    def test_timed_night_offset_before_start(self) -> None:
        # Night: 21:00 - 60 min = 20:00
        shift_date = date(2025, 6, 15)
        result = reminder_service.get_reminder_time(
            shift_date, {"start": "21:00", "end": "08:00", "same_day": False, "all_day": False}
        )
        assert result is not None
        assert result == datetime(2025, 6, 15, 20, 0)

    def test_08_00_08_00_uses_am_offset(self) -> None:
        # Timed 08:00–08:00 is classified as AM → reminder at 08:00 + 30 min = 08:30
        shift_date = date(2025, 6, 15)
        result = reminder_service.get_reminder_time(
            shift_date, {"start": "08:00", "end": "08:00", "all_day": False}
        )
        assert result is not None
        assert result.date() == shift_date
        assert result.time() == time(8, 30)


class TestEventToShiftInfo:
    """Tests for _event_to_shift_info (calendar event -> (date, shift_info))."""

    def test_all_day_event(self) -> None:
        event = {"start": {"date": "2025-06-15"}, "end": {"date": "2025-06-16"}}
        result = _event_to_shift_info(event, "Australia/Sydney")
        assert result is not None
        shift_date, shift_info = result
        assert shift_date == date(2025, 6, 15)
        assert shift_info["all_day"] is True
        assert "summary" in shift_info  # reminder_job adds summary (None when missing)

    def test_timed_event(self) -> None:
        event = {
            "start": {"dateTime": "2025-06-15T07:30:00+10:00"},
            "end": {"dateTime": "2025-06-15T15:30:00+10:00"},
        }
        result = _event_to_shift_info(event, "Australia/Sydney")
        assert result is not None
        shift_date, shift_info = result
        assert shift_date == date(2025, 6, 15)
        assert shift_info["start"] == "07:30"
        assert shift_info["end"] == "15:30"
        assert shift_info["all_day"] is False
        assert shift_info["same_day"] is True

    def test_timed_event_overnight(self) -> None:
        event = {
            "start": {"dateTime": "2025-06-15T21:00:00+10:00"},
            "end": {"dateTime": "2025-06-16T08:00:00+10:00"},
        }
        result = _event_to_shift_info(event, "Australia/Sydney")
        assert result is not None
        shift_date, shift_info = result
        assert shift_date == date(2025, 6, 15)
        assert shift_info["same_day"] is False

    def test_missing_date_time_returns_none(self) -> None:
        event = {"start": {}, "end": {}}
        assert _event_to_shift_info(event, "UTC") is None

    def test_invalid_date_returns_none(self) -> None:
        event = {"start": {"date": "not-a-date"}, "end": {"date": "2025-06-16"}}
        assert _event_to_shift_info(event, "UTC") is None
