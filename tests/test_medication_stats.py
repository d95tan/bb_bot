"""Unit tests for medication stats (SQLite-backed streaks and adherence)."""

from datetime import date, timedelta
from pathlib import Path
import pytest

from src.services import medication_stats

# Fixed "today" for deterministic tests
FIXED_TODAY = date(2025, 6, 15)


@pytest.fixture(autouse=True)
def isolate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a temp DB and fixed today so tests don't touch real data or system date."""
    monkeypatch.setattr(medication_stats, "_DB_PATH", tmp_path / "medication_stats.db")
    monkeypatch.setattr(medication_stats, "_today_app_tz", lambda: FIXED_TODAY)


class TestRecordTaken:
    """Tests for record_taken."""

    def test_record_taken_stores_date(self) -> None:
        medication_stats.record_taken(12345, FIXED_TODAY)
        assert medication_stats.get_current_streak(12345) == 1

    def test_record_taken_idempotent(self) -> None:
        medication_stats.record_taken(999, FIXED_TODAY)
        medication_stats.record_taken(999, FIXED_TODAY)
        assert medication_stats.get_current_streak(999) == 1

    def test_record_taken_multiple_dates(self) -> None:
        medication_stats.record_taken(1, date(2025, 6, 14))
        medication_stats.record_taken(1, FIXED_TODAY)
        assert medication_stats.get_current_streak(1) == 2

    def test_different_users_isolated(self) -> None:
        medication_stats.record_taken(100, FIXED_TODAY)
        medication_stats.record_taken(200, FIXED_TODAY)
        assert medication_stats.get_current_streak(100) == 1
        assert medication_stats.get_current_streak(200) == 1


class TestGetCurrentStreak:
    """Tests for get_current_streak."""

    def test_no_data_returns_zero(self) -> None:
        assert medication_stats.get_current_streak(99999) == 0

    def test_today_only_streak_one(self) -> None:
        medication_stats.record_taken(1, FIXED_TODAY)
        assert medication_stats.get_current_streak(1) == 1

    def test_consecutive_days_ending_today(self) -> None:
        for i in range(5):
            medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=i))
        assert medication_stats.get_current_streak(1) == 5

    def test_gap_before_today_breaks_streak(self) -> None:
        medication_stats.record_taken(1, FIXED_TODAY)
        medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=2))  # skip yesterday
        # Streak is only today
        assert medication_stats.get_current_streak(1) == 1

    def test_yesterday_but_not_today_returns_zero(self) -> None:
        medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=1))
        assert medication_stats.get_current_streak(1) == 0


class TestGetLongestStreak:
    """Tests for get_longest_streak."""

    def test_no_data_returns_zero(self) -> None:
        assert medication_stats.get_longest_streak(99999) == 0

    def test_single_day_returns_one(self) -> None:
        medication_stats.record_taken(1, FIXED_TODAY)
        assert medication_stats.get_longest_streak(1) == 1

    def test_consecutive_run(self) -> None:
        for i in range(4):
            medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=i))
        assert medication_stats.get_longest_streak(1) == 4

    def test_two_runs_returns_longest(self) -> None:
        # Run 1: 3 days
        for i in range(3):
            medication_stats.record_taken(1, date(2025, 6, 1) + timedelta(days=i))
        # Run 2: 5 days (longer)
        for i in range(5):
            medication_stats.record_taken(1, date(2025, 6, 10) + timedelta(days=i))
        assert medication_stats.get_longest_streak(1) == 5

    def test_gap_in_middle_breaks_run(self) -> None:
        medication_stats.record_taken(1, date(2025, 6, 10))
        medication_stats.record_taken(1, date(2025, 6, 11))
        medication_stats.record_taken(1, date(2025, 6, 13))  # gap on 12th
        medication_stats.record_taken(1, date(2025, 6, 14))
        assert medication_stats.get_longest_streak(1) == 2


class TestGetAdherenceRate:
    """Tests for get_adherence_rate (last N days)."""

    def test_no_data_returns_zero(self) -> None:
        assert medication_stats.get_adherence_rate(99999, days=30) == pytest.approx(0.0)

    def test_one_day_in_30(self) -> None:
        medication_stats.record_taken(1, FIXED_TODAY)
        rate = medication_stats.get_adherence_rate(1, days=30)
        assert rate == pytest.approx(1 / 30)

    def test_all_30_days(self) -> None:
        for i in range(30):
            medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=i))
        assert medication_stats.get_adherence_rate(1, days=30) == pytest.approx(1.0)

    def test_half_the_days(self) -> None:
        for i in range(0, 30, 2):
            medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=i))
        assert medication_stats.get_adherence_rate(1, days=30) == pytest.approx(15 / 30)

    def test_days_outside_window_ignored(self) -> None:
        medication_stats.record_taken(1, FIXED_TODAY - timedelta(days=40))
        assert medication_stats.get_adherence_rate(1, days=30) == pytest.approx(0.0)
