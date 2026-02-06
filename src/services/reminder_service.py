"""
Shift reminder service.

Sends reminders based on shift groups (AM / PM / Night / Off) defined in shifts.yaml.
Reminder time = shift start + reminder_minutes (negative = before start).
Reminders continue until acknowledged.

Acknowledgment state: if REDIS_URL is set, uses Redis (shared across instances and
survives restarts). Otherwise uses a JSON file in data/ (single instance; mount
volume in Docker for persistence).

With Redis, reminder *sending* is also coordinated: only one instance acquires
the "send slot" for a given (user, reminder time), so multiple instances do not
spam duplicate reminders.
"""

import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

from src.config import get_settings, get_shift_config
from src.constants import REMINDER_ACK_TTL_SECONDS

logger = logging.getLogger(__name__)

_ACK_FILE = Path("data/reminder_acknowledgments.json")
_REDIS_KEY_PREFIX = "bb_bot:reminder_ack"
_REDIS_SENT_PREFIX = "bb_bot:reminder_sent"

_pending_reminders: dict[int, datetime] = {}


def _redis_client() -> Optional[Any]:
    """Return Redis client if REDIS_URL is set, else None. Uses file store if Redis fails."""
    url = get_settings().redis_url
    if not url:
        return None
    try:
        import redis  # type: ignore[import-untyped]
        return redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("Redis unavailable (%s), using file store", e)
        return None


def _ack_key(user_id: int, d: date) -> str:
    """Redis key for one user's acknowledgment on a given date."""
    return f"{_REDIS_KEY_PREFIX}:{user_id}:{d.isoformat()}"


def _sent_slot_key(user_id: int, reminder_dt: datetime) -> str:
    """Redis key for 'this reminder was sent' (one per user per minute)."""
    slot = reminder_dt.strftime("%Y-%m-%dT%H:%M")
    return f"{_REDIS_SENT_PREFIX}:{user_id}:{slot}"


# --- File-backed store (used when Redis is not configured) ---

def _load_acknowledged_file() -> set[str]:
    """Load acknowledged keys (user_id:date) from JSON file."""
    if not _ACK_FILE.exists():
        return set()
    try:
        with open(_ACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("acknowledged", []))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load reminder acknowledgments: %s", e)
        return set()


def _save_acknowledged_file(acknowledged: set[str]) -> None:
    """Persist acknowledged set to JSON file."""
    _ACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_ACK_FILE, "w", encoding="utf-8") as f:
            json.dump({"acknowledged": list(acknowledged)}, f, indent=0)
    except OSError as e:
        logger.warning("Could not save reminder acknowledgments: %s", e)


def _get_acknowledged_cache() -> set[str]:
    """Lazy-load file-backed acknowledged set (caller may mutate; call _save after)."""
    if not hasattr(_get_acknowledged_cache, "_cache"):
        _get_acknowledged_cache._cache = _load_acknowledged_file()
    return _get_acknowledged_cache._cache


# --- Public API (Redis or file) ---

def get_shift_group(shift_info: dict) -> str:
    """Classify shift into am, pm, night, or off (uses ShiftConfig shift_groups)."""
    return get_shift_config().get_shift_group(shift_info)


def get_reminder_minutes(shift_info: dict) -> Optional[int]:
    """
    Minutes from shift start when to send the first reminder.
    Positive = after start, negative = before start. None = no reminder (e.g. off).
    """
    group = get_shift_group(shift_info)
    return get_shift_config().get_reminder_minutes(group)


def get_reminder_time(shift_date: date, shift_info: dict) -> Optional[datetime]:
    """
    Compute the datetime when the first reminder should be sent for this shift.
    Uses shift_groups: reminder_minutes for timed shifts, reminder_at for off days.
    Returns None if no reminder.
    """
    if shift_info.get("all_day"):
        # Off day: use fixed time from shift_groups.off.reminder_at
        at_str = get_shift_config().get_off_day_reminder_at()
        if not at_str:
            return None
        parts = at_str.split(":")
        hour = int(parts[0]) if parts else 0
        minute = int(parts[1]) if len(parts) > 1 else 0
        return datetime.combine(shift_date, time(hour, minute))
    minutes = get_reminder_minutes(shift_info)
    if minutes is None:
        return None
    start_str = shift_info.get("start", "09:00")
    parts = start_str.split(":")
    hour = int(parts[0]) if parts else 0
    minute = int(parts[1]) if len(parts) > 1 else 0
    shift_start = datetime.combine(shift_date, time(hour, minute))
    reminder_dt = shift_start + timedelta(minutes=minutes)
    return reminder_dt


def get_medication_window(shift_type: str) -> Optional[tuple[time, time]]:
    """
    Get the medication reminder window based on shift type (legacy helper).
    Prefer get_reminder_time(shift_date, shift_info) with shift_groups instead.
    """
    shift_config = get_shift_config()
    shift_info = shift_config.get_shift_by_code(shift_type) if shift_config.code_mappings else None
    if not shift_info:
        return None
    if shift_info.get("all_day"):
        return None
    start_str = shift_info.get("start", "09:00")
    start_hour, start_min = map(int, start_str.split(":"))
    window_start = time(start_hour, start_min)
    end_hour = start_hour + 1
    end_min = start_min + 30
    if end_min >= 60:
        end_hour += 1
        end_min -= 60
    if end_hour >= 24:
        end_hour, end_min = 23, 59
    window_end = time(end_hour, end_min)
    return (window_start, window_end)


def is_within_window(current_time: time, window: tuple[time, time]) -> bool:
    """Check if current time is within the medication window."""
    start, end = window
    return start <= current_time <= end


def acknowledge_medication(user_id: int) -> None:
    """Mark medication as taken for today; persist to Redis or file."""
    today = date.today()
    r = _redis_client()
    if r is not None:
        try:
            key = _ack_key(user_id, today)
            r.set(key, "1", ex=REMINDER_ACK_TTL_SECONDS)
        except Exception as e:
            logger.warning("Redis set failed: %s", e)
    else:
        ack = _get_acknowledged_cache()
        ack.add(f"{user_id}:{today.isoformat()}")
        _save_acknowledged_file(ack)
    if user_id in _pending_reminders:
        del _pending_reminders[user_id]
    logger.info("Medication acknowledged for user %s", user_id)


def try_acquire_reminder_slot(user_id: int, reminder_dt: datetime) -> bool:
    """
    Try to acquire the right to send this reminder (multi-instance safe).
    Call this before sending; if True, this instance won the race and should send.
    If False, another instance is sending or already sent for this slot — skip.
    When Redis is not configured, always returns True (single instance).
    """
    r = _redis_client()
    if r is None:
        return True
    key = _sent_slot_key(user_id, reminder_dt)
    ttl = get_settings().reminder_sent_slot_ttl_seconds
    try:
        # SET key "1" NX EX TTL: set only if key does not exist; then expire
        return bool(r.set(key, "1", nx=True, ex=ttl))
    except Exception as e:
        logger.warning("Redis set NX failed: %s", e)
        return True  # allow send on Redis error to avoid silencing reminders


def is_medication_acknowledged(user_id: int) -> bool:
    """Check if medication has been acknowledged today (Redis or file)."""
    today = date.today()
    r = _redis_client()
    if r is not None:
        try:
            return bool(r.exists(_ack_key(user_id, today)))
        except Exception as e:
            logger.warning("Redis exists failed: %s", e)
            return False
    key = f"{user_id}:{today.isoformat()}"
    return key in _get_acknowledged_cache()


def clear_old_acknowledgments() -> None:
    """Remove acknowledgment keys from previous days (file store only; Redis keys expire)."""
    r = _redis_client()
    if r is not None:
        return
    today = date.today().isoformat()
    ack = _get_acknowledged_cache()
    kept = {k for k in ack if ":" in k and k.rsplit(":", 1)[-1] == today}
    if len(kept) != len(ack):
        ack.clear()
        ack.update(kept)
        _save_acknowledged_file(ack)
        logger.debug("Cleared old acknowledgments")
