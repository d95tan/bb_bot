"""Unit tests for reminder service and reminder job helpers."""

from datetime import date, datetime, time
from unittest.mock import MagicMock, patch

from src.services import reminder_service
from src.bot.reminder_job import _event_to_shift_info


class TestGetShiftGroup:
    """Tests for get_shift_group classification."""

    def test_all_day_is_off(self) -> None:
        assert reminder_service.get_shift_group({"all_day": True}) == "off"

    def test_am_by_start_time(self) -> None:
        # Before 12:00
        assert reminder_service.get_shift_group({"start": "07:30", "all_day": False}) == "am"
        assert reminder_service.get_shift_group({"start": "09:00", "all_day": False}) == "am"

    def test_pm_by_start_time(self) -> None:
        # 12:00 up to (but not including) 19:00
        assert reminder_service.get_shift_group({"start": "13:30", "all_day": False}) == "pm"
        assert reminder_service.get_shift_group({"start": "12:00", "all_day": False}) == "pm"
        assert reminder_service.get_shift_group({"start": "18:30", "all_day": False}) == "pm"

    def test_night_by_start_time(self) -> None:
        # 19:00 onwards
        assert reminder_service.get_shift_group({"start": "21:00", "all_day": False}) == "night"
        assert reminder_service.get_shift_group({"start": "19:00", "all_day": False}) == "night"


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
        # Off day: reminder time comes from get_off_day_reminder_at() (fixed HH:MM)
        shift_date = date(2025, 6, 15)
        mock_config = MagicMock()
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


class TestEventToShiftInfo:
    """Tests for _event_to_shift_info (calendar event -> (date, shift_info))."""

    def test_all_day_event(self) -> None:
        event = {"start": {"date": "2025-06-15"}, "end": {"date": "2025-06-16"}}
        result = _event_to_shift_info(event, "Australia/Sydney")
        assert result is not None
        shift_date, shift_info = result
        assert shift_date == date(2025, 6, 15)
        assert shift_info == {"all_day": True}

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
