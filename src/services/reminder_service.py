"""
Medication reminder service (stub for future implementation).

This service will send periodic reminders for medication based on the user's
shift schedule. Reminders continue every 30 minutes until acknowledged.

NOTE: This is a stub implementation. The actual reminder logic will be
implemented when the medication feature is activated.
"""

import logging
from datetime import datetime, time
from typing import Optional

from src.config import get_shift_config


logger = logging.getLogger(__name__)


# In-memory state for tracking medication acknowledgments (resets on restart)
_pending_reminders: dict[int, datetime] = {}  # user_id -> scheduled_time
_acknowledged: set[str] = set()  # Set of "user_id:date" strings


def get_medication_window(shift_type: str) -> Optional[tuple[time, time]]:
    """
    Get the medication reminder window based on shift type.
    
    Returns a tuple of (start_time, end_time) or None if no medication
    is needed for this shift type.
    
    The logic here is:
    - AM shift: Take medication at start of shift (07:30 - 09:00)
    - PM shift: Take medication at start of shift (13:30 - 15:00)
    - Night shift: Take medication before shift (20:00 - 21:00)
    - Off/Annual Leave: No scheduled medication
    - Training: Same as AM shift (08:00 - 09:30)
    """
    shift_config = get_shift_config()
    shift_info = shift_config.get_shift(shift_type)
    
    if not shift_info:
        return None
    
    # Skip all-day events (Off, Annual Leave)
    if shift_info.get("all_day"):
        return None
    
    # Get shift start time
    start_str = shift_info.get("start", "09:00")
    start_hour, start_min = map(int, start_str.split(":"))
    
    # Medication window is from shift start to 1.5 hours after
    window_start = time(start_hour, start_min)
    
    # Calculate end time (1.5 hours later)
    end_hour = start_hour + 1
    end_min = start_min + 30
    if end_min >= 60:
        end_hour += 1
        end_min -= 60
    if end_hour >= 24:
        end_hour = 23
        end_min = 59
    
    window_end = time(end_hour, end_min)
    
    return (window_start, window_end)


def is_within_window(current_time: time, window: tuple[time, time]) -> bool:
    """Check if current time is within the medication window."""
    start, end = window
    return start <= current_time <= end


def acknowledge_medication(user_id: int) -> None:
    """Mark medication as taken for today."""
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"{user_id}:{today}"
    _acknowledged.add(key)
    
    # Clear pending reminder
    if user_id in _pending_reminders:
        del _pending_reminders[user_id]
    
    logger.info(f"Medication acknowledged for user {user_id}")


def is_medication_acknowledged(user_id: int) -> bool:
    """Check if medication has been acknowledged today."""
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"{user_id}:{today}"
    return key in _acknowledged


def clear_old_acknowledgments() -> None:
    """Clear acknowledgments from previous days."""
    _acknowledged.clear()


# Future implementation notes:
#
# To fully implement medication reminders:
#
# 1. Add APScheduler back to requirements.txt
#
# 2. Create a scheduler that runs every 30 minutes:
#    - Check if user has a shift today (from Google Calendar)
#    - Determine medication window from shift type
#    - If within window and not acknowledged, send reminder
#
# 3. Add Telegram inline button for acknowledgment:
#    - Button callback: "med_ack"
#    - Handler calls acknowledge_medication()
#
# 4. Add commands:
#    - /medication_on - Enable reminders
#    - /medication_off - Disable reminders
#    - /took_medication - Manual acknowledgment
