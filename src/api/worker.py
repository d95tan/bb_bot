"""Background reminder worker for the API process."""

from __future__ import annotations

import asyncio
import logging

from src.app.reminders import find_due_reminders
from src.bot.replies import REMINDER_MESSAGE
from src.config import get_settings
from src.notifiers.telegram import TelegramNotifier
from src.services.accounts import seed_authorized_accounts

logger = logging.getLogger(__name__)


async def run_reminder_cycle(notifier: TelegramNotifier | None = None) -> int:
    """Find due reminders and send them. Returns number sent."""
    notifier = notifier or TelegramNotifier()
    due = await find_due_reminders()
    sent = 0
    for item in due:
        if item.telegram_chat_id is None:
            logger.warning(
                "No telegram binding for account %s; skip send", item.account_id
            )
            continue
        try:
            await notifier.send_medication_reminder(
                item.telegram_chat_id, REMINDER_MESSAGE
            )
            sent += 1
        except Exception as e:
            logger.warning(
                "Failed to send reminder to account %s: %s", item.account_id, e
            )
    return sent


async def reminder_worker(stop_event: asyncio.Event) -> None:
    """Loop: sleep interval, then run reminder cycle until stop_event is set."""
    seed_authorized_accounts()
    settings = get_settings()
    interval = max(5, settings.reminder_job_interval_seconds)
    logger.info("Reminder worker started (interval=%ss)", interval)

    # First run soon, matching previous PTB job behavior
    first = min(30, max(5, interval // 10))
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=first)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            if settings.is_calendar_configured:
                sent = await run_reminder_cycle()
                if sent:
                    logger.info("Reminder cycle sent %s message(s)", sent)
            else:
                logger.debug("Calendar not configured; reminder cycle skipped")
        except Exception as e:
            logger.exception("Reminder cycle failed: %s", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            continue

    logger.info("Reminder worker stopped")
