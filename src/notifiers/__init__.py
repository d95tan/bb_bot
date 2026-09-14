"""Outbound notification adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """Channel-agnostic outbound messaging."""

    async def send_medication_reminder(
        self, chat_id: int, text: str
    ) -> None:
        """Send a medication reminder with an acknowledge action."""
        ...
