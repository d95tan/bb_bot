"""
Account identity and channel bindings.

v1: account_id equals the Telegram user id for seeded users so existing
medication_stats / reminder ack keys keep working without a data rewrite.
Bindings leave room for Discord (and other channels) later.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from src.config import get_settings

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/accounts.db")

CHANNEL_TELEGRAM = "telegram"


def _get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id INTEGER PRIMARY KEY
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_bindings (
            channel TEXT NOT NULL,
            external_id TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            PRIMARY KEY (channel, external_id),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        )
        """
    )
    conn.commit()
    return conn


def ensure_telegram_account(telegram_user_id: int) -> int:
    """
    Return account_id for a Telegram user, creating account + binding if needed.

    v1 uses telegram_user_id as account_id so legacy stats/ack rows remain valid.
    """
    account_id = telegram_user_id
    external_id = str(telegram_user_id)
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (account_id) VALUES (?)",
            (account_id,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO channel_bindings (channel, external_id, account_id)
            VALUES (?, ?, ?)
            """,
            (CHANNEL_TELEGRAM, external_id, account_id),
        )
        conn.commit()
    finally:
        conn.close()
    return account_id


def get_account_id_for_telegram(telegram_user_id: int) -> int | None:
    """Look up account_id for a Telegram user id, or None if unbound."""
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT account_id FROM channel_bindings
            WHERE channel = ? AND external_id = ?
            """,
            (CHANNEL_TELEGRAM, str(telegram_user_id)),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def get_telegram_id_for_account(account_id: int) -> int | None:
    """Look up Telegram chat/user id bound to an account, or None."""
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT external_id FROM channel_bindings
            WHERE channel = ? AND account_id = ?
            """,
            (CHANNEL_TELEGRAM, account_id),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def resolve_telegram_account(telegram_user_id: int) -> int | None:
    """
    Resolve Telegram user to account_id.

    Authorized users are auto-seeded; unknown users return None.
    """
    settings = get_settings()
    if telegram_user_id not in settings.authorized_user_ids:
        return None
    existing = get_account_id_for_telegram(telegram_user_id)
    if existing is not None:
        return existing
    return ensure_telegram_account(telegram_user_id)


def seed_authorized_accounts() -> None:
    """Ensure every authorized Telegram user has an account + binding."""
    settings = get_settings()
    for telegram_user_id in settings.authorized_user_ids:
        ensure_telegram_account(telegram_user_id)
    logger.info(
        "Seeded %s telegram account binding(s)",
        len(settings.authorized_user_ids),
    )


def list_authorized_account_ids() -> list[int]:
    """Account ids for all authorized Telegram users (seeds bindings first)."""
    seed_authorized_accounts()
    return [ensure_telegram_account(uid) for uid in get_settings().authorized_user_ids]
