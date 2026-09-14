"""HTTP API endpoint tests (FastAPI TestClient).

These exercise route wiring, auth, and response shapes — not Google/Telegram.
External use cases are mocked where they would hit Calendar/OCR.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.app.medication import AckResult, MedicationStats
from src.app.schedules import ScheduleEvent, ScheduleLine, UploadResult
from src.config import Settings


API_KEY = "test-api-key"
AUTH_USER = 424242


def _make_settings(**overrides) -> Settings:
    """Build Settings without reading a real .env."""
    data = {
        "telegram_bot_token": "test-token",
        "telegram_user_ids": str(AUTH_USER),
        "api_key": API_KEY,
        "google_client_id": "cid",
        "google_client_secret": "csecret",
        "google_refresh_token": "refresh-token",
        "enable_calendar_upload": True,
        "redis_url": None,
        "reminder_job_interval_seconds": 3600,
    }
    data.update(overrides)
    return Settings(**data)


@pytest.fixture()
def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate settings + DBs and skip the reminder background worker."""
    import src.config as config_mod
    from src.services import accounts, medication_stats, reminder_service

    settings = _make_settings()
    monkeypatch.setattr(config_mod, "_settings", settings)
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

    monkeypatch.setattr(accounts, "_DB_PATH", tmp_path / "accounts.db")
    monkeypatch.setattr(medication_stats, "_DB_PATH", tmp_path / "medication_stats.db")
    monkeypatch.setattr(
        medication_stats, "_today_app_tz", lambda: date(2025, 6, 15)
    )
    monkeypatch.setattr(
        reminder_service, "_today_app_tz", lambda: date(2025, 6, 15)
    )
    monkeypatch.setattr(reminder_service, "_ACK_FILE", tmp_path / "acks.json")
    reminder_service._pending_reminders.clear()
    if hasattr(reminder_service._get_acknowledged_cache, "_cache"):
        delattr(reminder_service._get_acknowledged_cache, "_cache")
    reminder_service._last_sent_slot.clear()

    async def _noop_worker(stop_event):
        await stop_event.wait()

    monkeypatch.setattr("src.api.lifespan.reminder_worker", _noop_worker)
    monkeypatch.setattr("src.api.lifespan.seed_authorized_accounts", lambda: None)

    # Fresh app so lifespan picks up patches
    from src.api.app import create_app

    with TestClient(create_app()) as client:
        yield client, settings


def _auth(_client: TestClient) -> dict:
    return {"X-API-Key": API_KEY}


class TestHealth:
    def test_health_ok_without_api_key(self, api_env) -> None:
        client, _ = api_env
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["calendar_configured"] is True

    def test_health_calendar_not_configured(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        new_settings = _make_settings(google_refresh_token=None)
        monkeypatch.setattr("src.api.routers.health.get_settings", lambda: new_settings)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["calendar_configured"] is False


class TestApiKeyAuth:
    def test_schedules_requires_api_key(self, api_env) -> None:
        client, _ = api_env
        response = client.get("/schedules")
        assert response.status_code == 401

    def test_wrong_api_key_rejected(self, api_env) -> None:
        client, _ = api_env
        response = client.get("/schedules", headers={"X-API-Key": "wrong"})
        assert response.status_code == 401

    def test_ack_requires_api_key(self, api_env) -> None:
        client, _ = api_env
        response = client.post(
            "/medication/ack",
            json={"telegram_user_id": AUTH_USER},
        )
        assert response.status_code == 401


class TestListSchedules:
    def test_list_schedules_returns_events(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        events = [
            ScheduleEvent(summary="AM Shift", date_part="2025-06-16", time_part="07:30"),
            ScheduleEvent(summary="Off", date_part="2025-06-17", time_part=None),
        ]
        monkeypatch.setattr(
            "src.api.routers.schedules.schedules_app.get_upcoming_schedule",
            AsyncMock(return_value=events),
        )

        response = client.get("/schedules", headers=_auth(client), params={"weeks": 4})
        assert response.status_code == 200
        body = response.json()
        assert body["calendar_configured"] is True
        assert len(body["events"]) == 2
        assert body["events"][0] == {
            "summary": "AM Shift",
            "date_part": "2025-06-16",
            "time_part": "07:30",
        }
        assert body["events"][1]["time_part"] is None

    def test_list_schedules_calendar_not_configured(
        self, api_env, monkeypatch
    ) -> None:
        client, _ = api_env
        new_settings = _make_settings(google_refresh_token=None)
        monkeypatch.setattr(
            "src.api.routers.schedules.get_settings", lambda: new_settings
        )

        response = client.get("/schedules", headers=_auth(client))
        assert response.status_code == 200
        body = response.json()
        assert body["calendar_configured"] is False
        assert body["events"] == []

    def test_list_schedules_invalid_weeks(self, api_env) -> None:
        client, _ = api_env
        response = client.get(
            "/schedules", headers=_auth(client), params={"weeks": 99}
        )
        assert response.status_code == 422


class TestUploadSchedule:
    def test_upload_returns_lines_and_stats(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        result = UploadResult(
            empty=False,
            dry_run=False,
            lines=[
                ScheduleLine(
                    shift_date=date(2025, 6, 16),
                    label="Mon 16 Jun: AM",
                    status="created",
                )
            ],
            stats={"created": 1, "skipped": 0, "updated": 0, "failed": 0, "unknown": 0},
        )
        monkeypatch.setattr(
            "src.api.routers.schedules.schedules_app.upload_schedule_image",
            AsyncMock(return_value=result),
        )

        response = client.post(
            "/schedules/upload",
            headers=_auth(client),
            files={"file": ("schedule.jpg", b"fake-image-bytes", "image/jpeg")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["empty"] is False
        assert body["dry_run"] is False
        assert body["stats"]["created"] == 1
        assert body["lines"][0]["label"] == "Mon 16 Jun: AM"
        assert body["lines"][0]["status"] == "created"
        assert body["lines"][0]["shift_date"] == "2025-06-16"

    def test_upload_empty_image_bytes(self, api_env) -> None:
        client, _ = api_env
        response = client.post(
            "/schedules/upload",
            headers=_auth(client),
            files={"file": ("empty.jpg", b"", "image/jpeg")},
        )
        assert response.status_code == 400

    def test_upload_empty_ocr_result(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        monkeypatch.setattr(
            "src.api.routers.schedules.schedules_app.upload_schedule_image",
            AsyncMock(return_value=UploadResult(empty=True)),
        )
        response = client.post(
            "/schedules/upload",
            headers=_auth(client),
            files={"file": ("schedule.jpg", b"bytes", "image/jpeg")},
        )
        assert response.status_code == 200
        assert response.json()["empty"] is True

    def test_upload_503_when_calendar_required_but_missing(
        self, api_env, monkeypatch
    ) -> None:
        client, _ = api_env
        new_settings = _make_settings(
            google_refresh_token=None,
            enable_calendar_upload=True,
        )
        monkeypatch.setattr(
            "src.api.routers.schedules.get_settings", lambda: new_settings
        )

        response = client.post(
            "/schedules/upload",
            headers=_auth(client),
            files={"file": ("schedule.jpg", b"bytes", "image/jpeg")},
        )
        assert response.status_code == 503


class TestMedicationAckAndStats:
    def test_ack_unauthorized_user(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        monkeypatch.setattr(
            "src.api.routers.medication.resolve_telegram_account",
            lambda telegram_user_id: None,
        )
        response = client.post(
            "/medication/ack",
            headers=_auth(client),
            json={"telegram_user_id": 999},
        )
        assert response.status_code == 403

    def test_ack_success_returns_streak(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        monkeypatch.setattr(
            "src.api.routers.medication.resolve_telegram_account",
            lambda telegram_user_id: AUTH_USER,
        )
        monkeypatch.setattr(
            "src.api.routers.medication.medication_app.acknowledge_medication",
            lambda account_id, shift_date=None: AckResult(
                account_id=account_id, streak=3
            ),
        )
        response = client.post(
            "/medication/ack",
            headers=_auth(client),
            json={"telegram_user_id": AUTH_USER},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["account_id"] == AUTH_USER
        assert body["streak"] == 3

    def test_stats_success(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        monkeypatch.setattr(
            "src.api.routers.medication.resolve_telegram_account",
            lambda telegram_user_id: AUTH_USER,
        )
        monkeypatch.setattr(
            "src.api.routers.medication.medication_app.get_medication_stats",
            lambda account_id, days=30: MedicationStats(
                account_id=account_id,
                current_streak=2,
                longest_streak=5,
                adherence_rate=0.5,
                days=days,
            ),
        )
        response = client.get(
            "/medication/stats",
            headers=_auth(client),
            params={"telegram_user_id": AUTH_USER, "days": 30},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["current_streak"] == 2
        assert body["longest_streak"] == 5
        assert body["adherence_rate"] == 0.5
        assert body["days"] == 30

    def test_stats_unauthorized(self, api_env, monkeypatch) -> None:
        client, _ = api_env
        monkeypatch.setattr(
            "src.api.routers.medication.resolve_telegram_account",
            lambda telegram_user_id: None,
        )
        response = client.get(
            "/medication/stats",
            headers=_auth(client),
            params={"telegram_user_id": 1},
        )
        assert response.status_code == 403

    def test_ack_then_stats_integration(self, api_env, monkeypatch) -> None:
        """End-to-end through real medication/reminder services + account resolve."""
        client, _ = api_env
        from src.services import accounts

        accounts.ensure_telegram_account(AUTH_USER)
        monkeypatch.setattr(
            "src.api.routers.medication.resolve_telegram_account",
            lambda telegram_user_id: (
                AUTH_USER if telegram_user_id == AUTH_USER else None
            ),
        )

        ack = client.post(
            "/medication/ack",
            headers=_auth(client),
            json={"telegram_user_id": AUTH_USER},
        )
        assert ack.status_code == 200
        assert ack.json()["streak"] >= 1

        stats = client.get(
            "/medication/stats",
            headers=_auth(client),
            params={"telegram_user_id": AUTH_USER},
        )
        assert stats.status_code == 200
        body = stats.json()
        assert body["current_streak"] >= 1
        assert body["longest_streak"] >= 1
