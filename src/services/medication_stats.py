"""
Persistent medication-taking stats (SQLite).

Records each acknowledgment by (user_id, date) and provides:
- current streak (consecutive days ending today)
- longest streak ever
- adherence rate (e.g. last 30 days).
"""

import sqlite3
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import get_settings

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/medication_stats.db")


def _today_app_tz() -> date:
    """Today's date in the application timezone."""
    tz = ZoneInfo(get_settings().timezone)
    return datetime.now(tz).date()


def _get_connection() -> sqlite3.Connection:
    """Open DB and ensure table exists; creates data/ if needed."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS medication_taken (
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            PRIMARY KEY (user_id, date)
        )
        """
    )
    conn.commit()
    return conn


def record_taken(user_id: int, d: date | None = None) -> None:
    """
    Args:
     user_id(int): Account id (v1: Telegram user id).
     d(date | None): Date taken. Defaults to today in the app timezone.

    Returns:
     None
    """
    if d is None:
        d = _today_app_tz()
    date_str = d.isoformat()
    try:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO medication_taken (user_id, date) VALUES (?, ?)",
                (user_id, date_str),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to record medication taken for user %s: %s", user_id, e)


def remove_taken(user_id: int, d: date) -> bool:
    """
    Args:
     user_id(int): Account id.
     d(date): Date to un-log.

    Returns:
     bool: True if a row was deleted.
    """
    date_str = d.isoformat()
    try:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM medication_taken WHERE user_id = ? AND date = ?",
                (user_id, date_str),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    except Exception as e:
        logger.warning(
            "Failed to remove medication taken for user %s on %s: %s",
            user_id,
            date_str,
            e,
        )
        return False


def list_taken_dates(user_id: int, start: date, end: date) -> list[date]:
    """
    Args:
     user_id(int): Account id.
     start(date): Inclusive window start.
     end(date): Inclusive window end.

    Returns:
     list[date]: Taken dates in the window, ascending.
    """
    try:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT date FROM medication_taken
                WHERE user_id = ? AND date >= ? AND date <= ?
                ORDER BY date ASC
                """,
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
            return [date.fromisoformat(r[0]) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to list taken dates for user %s: %s", user_id, e)
        return []


def get_day_statuses(user_id: int, days: int = 30) -> list[tuple[date, bool]]:
    """
    Args:
     user_id(int): Account id.
     days(int): Window length including today.

    Returns:
     list[tuple[date, bool]]: Each day in the window and whether it was taken.
    """
    today = _today_app_tz()
    start = today - timedelta(days=days - 1)
    taken = set(list_taken_dates(user_id, start, today))
    return [
        (start + timedelta(days=i), (start + timedelta(days=i)) in taken)
        for i in range(days)
    ]


def _all_taken_iso(user_id: int) -> set[str]:
    """Return all taken dates for a user as ISO strings."""
    try:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT date FROM medication_taken WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return {r[0] for r in rows}
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to load taken dates for user %s: %s", user_id, e)
        return set()


def _streak_ending_today(dates: set[str], today: date) -> int:
    """Consecutive days ending today from an ISO-date set. 0 if today missing."""
    if today.isoformat() not in dates:
        return 0
    streak = 0
    d = today
    while d.isoformat() in dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


def preview_current_streak(
    user_id: int,
    add_dates: list[date] | None = None,
    remove_dates: list[date] | None = None,
) -> int:
    """
    Args:
     user_id(int): Account id.
     add_dates(list[date] | None): Dates hypothetically logged.
     remove_dates(list[date] | None): Dates hypothetically un-logged.

    Returns:
     int: Current streak after the hypothetical changes (today must be taken).
    """
    today = _today_app_tz()
    dates = _all_taken_iso(user_id)
    for d in add_dates or []:
        dates.add(d.isoformat())
    for d in remove_dates or []:
        dates.discard(d.isoformat())
    return _streak_ending_today(dates, today)


def get_current_streak(user_id: int) -> int:
    """Consecutive days ending today (today, yesterday, ...). Returns 0 if today not taken."""
    try:
        return _streak_ending_today(_all_taken_iso(user_id), _today_app_tz())
    except Exception as e:
        logger.warning("Failed to get current streak for user %s: %s", user_id, e)
        return 0


def get_longest_streak(user_id: int) -> int:
    """Longest run of consecutive days with medication taken (ever)."""
    try:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT date FROM medication_taken WHERE user_id = ? ORDER BY date ASC",
                (user_id,),
            ).fetchall()
            if not rows:
                return 0
            dates = [date.fromisoformat(r[0]) for r in rows]
            best = 1
            current = 1
            for i in range(1, len(dates)):
                if (dates[i] - dates[i - 1]).days == 1:
                    current += 1
                else:
                    best = max(best, current)
                    current = 1
            return max(best, current)
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to get longest streak for user %s: %s", user_id, e)
        return 0


def get_adherence_rate(user_id: int, days: int = 30) -> float:
    """Fraction of the last `days` days (including today) on which medication was taken. 0.0–1.0."""
    today = _today_app_tz()
    start = today - timedelta(days=days - 1)
    try:
        conn = _get_connection()
        try:
            count = conn.execute(
                """
                SELECT COUNT(*) FROM medication_taken
                WHERE user_id = ? AND date >= ? AND date <= ?
                """,
                (user_id, start.isoformat(), today.isoformat()),
            ).fetchone()[0]
            return count / days if days else 0.0
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to get adherence rate for user %s: %s", user_id, e)
        return 0.0
