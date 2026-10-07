"""Tests for durable reminder send logging."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.services import reminder_sends


@pytest.fixture(autouse=True)
def isolate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reminder_sends, "_DB_PATH", tmp_path / "reminder_sends.db")


class TestRecordAndListSends:
    def test_lists_sends_for_app_timezone_day(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.services.reminder_sends.get_settings",
            lambda: type("S", (), {"timezone": "Asia/Singapore"})(),
        )
        reminder_sends.record_send(
            42,
            date(2025, 6, 15),
            datetime(2025, 6, 15, 9, 30),
            reminder_sends.SOURCE_JOB,
            sent_at=datetime(2025, 6, 15, 1, 31, tzinfo=timezone.utc),
        )
        # Previous calendar day in Singapore (UTC+8): 16:00 UTC on 14th → 00:00 SGT on 15th
        reminder_sends.record_send(
            42,
            date(2025, 6, 14),
            datetime(2025, 6, 14, 9, 30),
            reminder_sends.SOURCE_JOB,
            sent_at=datetime(2025, 6, 14, 1, 0, tzinfo=timezone.utc),
        )
        today = reminder_sends.list_sends_for_date(42, date(2025, 6, 15))
        assert len(today) == 1
        assert today[0].source == "job"
        assert today[0].shift_date == date(2025, 6, 15)

    def test_empty_when_none_sent(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.services.reminder_sends.get_settings",
            lambda: type("S", (), {"timezone": "Asia/Singapore"})(),
        )
        assert reminder_sends.list_sends_for_date(1, date(2025, 6, 15)) == []
