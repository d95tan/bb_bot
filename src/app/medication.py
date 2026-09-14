"""Medication acknowledgment and stats use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.services import medication_stats, reminder_service


@dataclass
class AckResult:
    """Result of acknowledging medication."""

    account_id: int
    streak: int


@dataclass
class MedicationStats:
    """Medication adherence summary for an account."""

    account_id: int
    current_streak: int
    longest_streak: int
    adherence_rate: float
    days: int = 30


def acknowledge_medication(
    account_id: int, shift_date: Optional[date] = None
) -> AckResult:
    """Mark medication taken for account; returns updated current streak."""
    reminder_service.acknowledge_medication(account_id, shift_date)
    streak = medication_stats.get_current_streak(account_id)
    return AckResult(account_id=account_id, streak=streak)


def get_medication_stats(account_id: int, days: int = 30) -> MedicationStats:
    """Return streak and adherence stats for an account."""
    return MedicationStats(
        account_id=account_id,
        current_streak=medication_stats.get_current_streak(account_id),
        longest_streak=medication_stats.get_longest_streak(account_id),
        adherence_rate=medication_stats.get_adherence_rate(account_id, days=days),
        days=days,
    )
