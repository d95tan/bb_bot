"""Tests for account identity / channel bindings."""

from pathlib import Path

import pytest

from src.services import accounts


@pytest.fixture()
def isolated_accounts_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "accounts.db"
    monkeypatch.setattr(accounts, "_DB_PATH", db)
    return db


def test_ensure_telegram_account_uses_telegram_id_as_account_id(
    isolated_accounts_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        accounts,
        "get_settings",
        lambda: type("S", (), {"authorized_user_ids": [42]})(),
    )
    account_id = accounts.ensure_telegram_account(42)
    assert account_id == 42
    assert accounts.get_account_id_for_telegram(42) == 42
    assert accounts.get_telegram_id_for_account(42) == 42


def test_resolve_unauthorized_returns_none(
    isolated_accounts_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        accounts,
        "get_settings",
        lambda: type("S", (), {"authorized_user_ids": [1]})(),
    )
    assert accounts.resolve_telegram_account(999) is None
