"""Telegram Bot API notifier (HTTP, no PTB Application)."""

from __future__ import annotations

import logging

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

_ACK_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "✓ I took it", "callback_data": "reminder_ack"}],
    ]
}


class TelegramNotifier:
    """Send messages via Telegram Bot API using the configured bot token."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or get_settings().telegram_bot_token

    async def send_medication_reminder(self, chat_id: int, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": _ACK_KEYBOARD,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                logger.warning(
                    "Telegram sendMessage failed for chat %s: %s %s",
                    chat_id,
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()
            logger.info("Sent medication reminder to chat %s", chat_id)
