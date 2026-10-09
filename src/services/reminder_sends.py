"""Durable log of medication reminders that were actually sent."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import get_settings

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/reminder_sends.db")

SOURCE_JOB = "job"
SOURCE_ADMIN = "admin"


@dataclass
class ReminderSend:
    """One successful reminder delivery."""

    account_id: int
    sent_at: datetime
    shift_date: date
    reminder_dt: datetime
    source: str


def _get_connection() -> sqlite3.Connection:
    """Open DB and ensure table exists; creates data/ if needed."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            shift_date TEXT NOT NULL,
            reminder_dt TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def record_send(
    account_id: int,
    shift_date: date,
    reminder_dt: datetime,
    source: str,
    sent_at: datetime | None = None,
) -> None:
    """
    Args:
     account_id(int): Patient account the reminder was sent to.
     shift_date(date): Shift date the reminder was for.
     reminder_dt(datetime): Scheduled reminder time (naive app-TZ or aware).
     source(str): ``job`` or ``admin``.
     sent_at(datetime | None): When the send succeeded. Defaults to UTC now.

    Returns:
     None
    """
    if sent_at is None:
        sent_at = datetime.now(timezone.utc)
    elif sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    else:
        sent_at = sent_at.astimezone(timezone.utc)
    reminder_iso = reminder_dt.isoformat()
    try:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO reminder_sends
                    (account_id, sent_at, shift_date, reminder_dt, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    sent_at.isoformat(),
                    shift_date.isoformat(),
                    reminder_iso,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to record reminder send for account %s: %s", account_id, e)


def list_sends_for_date(account_id: int, day: date) -> list[ReminderSend]:
    """
    Args:
     account_id(int): Patient account.
     day(date): Calendar day in the app timezone.

    Returns:
     list[ReminderSend]: Sends whose local (app TZ) date is ``day``, newest first.
    """
    tz = ZoneInfo(get_settings().timezone)
    try:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT account_id, sent_at, shift_date, reminder_dt, source
                FROM reminder_sends
                WHERE account_id = ?
                ORDER BY sent_at DESC
                """,
                (account_id,),
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to list reminder sends for account %s: %s", account_id, e)
        return []

    result: list[ReminderSend] = []
    for account_id_row, sent_at_s, shift_date_s, reminder_dt_s, source in rows:
        sent_at = datetime.fromisoformat(sent_at_s)
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        local_day = sent_at.astimezone(tz).date()
        if local_day != day:
            continue
        result.append(
            ReminderSend(
                account_id=int(account_id_row),
                sent_at=sent_at,
                shift_date=date.fromisoformat(shift_date_s),
                reminder_dt=datetime.fromisoformat(reminder_dt_s),
                source=str(source),
            )
        )
    return result
