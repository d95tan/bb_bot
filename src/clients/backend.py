"""HTTP client used by the Telegram bot to call the FastAPI backend."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


class BackendClient:
    """Thin async client for bb_bot API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.api_base_url).rstrip("/")
        self._api_key = api_key or settings.api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    def _admin_headers(self, admin_telegram_user_id: int) -> dict[str, str]:
        return {
            **self._headers(),
            "X-Admin-Telegram-User-Id": str(admin_telegram_user_id),
        }

    async def upload_schedule(
        self, image_bytes: bytes, filename: str = "schedule.jpg"
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/schedules/upload",
                headers=self._headers(),
                files={"file": (filename, image_bytes, "application/octet-stream")},
            )
            response.raise_for_status()
            return response.json()

    async def list_schedules(self, weeks: int = 4) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self._base_url}/schedules",
                headers=self._headers(),
                params={"weeks": weeks},
            )
            response.raise_for_status()
            return response.json()

    async def ack_medication(self, telegram_user_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/medication/ack",
                headers=self._headers(),
                json={"telegram_user_id": telegram_user_id},
            )
            response.raise_for_status()
            return response.json()

    async def medication_stats(
        self, telegram_user_id: int, days: int = 30
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/medication/stats",
                headers=self._headers(),
                params={"telegram_user_id": telegram_user_id, "days": days},
            )
            response.raise_for_status()
            return response.json()

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/health")
            response.raise_for_status()
            return response.json()

    async def admin_health(self, admin_telegram_user_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._base_url}/admin/health",
                headers=self._admin_headers(admin_telegram_user_id),
            )
            response.raise_for_status()
            return response.json()

    async def admin_reminder_status(
        self, admin_telegram_user_id: int
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/admin/reminders/status",
                headers=self._admin_headers(admin_telegram_user_id),
            )
            response.raise_for_status()
            return response.json()

    async def admin_trigger_reminder(
        self, admin_telegram_user_id: int
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/admin/reminders/trigger",
                headers=self._admin_headers(admin_telegram_user_id),
            )
            response.raise_for_status()
            return response.json()

    async def admin_patch(
        self,
        admin_telegram_user_id: int,
        start_date: str,
        end_date: str | None = None,
        note: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/admin/medication/patch",
                headers=self._admin_headers(admin_telegram_user_id),
                json={
                    "start_date": start_date,
                    "end_date": end_date,
                    "note": note,
                    "dry_run": dry_run,
                },
            )
            response.raise_for_status()
            return response.json()

    async def admin_unlog(
        self,
        admin_telegram_user_id: int,
        start_date: str,
        end_date: str | None = None,
        note: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/admin/medication/unlog",
                headers=self._admin_headers(admin_telegram_user_id),
                json={
                    "start_date": start_date,
                    "end_date": end_date,
                    "note": note,
                    "dry_run": dry_run,
                },
            )
            response.raise_for_status()
            return response.json()

    async def admin_stats(
        self, admin_telegram_user_id: int, days: int = 30
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/admin/medication/stats",
                headers=self._admin_headers(admin_telegram_user_id),
                params={"days": days},
            )
            response.raise_for_status()
            return response.json()

    async def admin_shifts(
        self, admin_telegram_user_id: int, days: int = 7
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self._base_url}/admin/shifts",
                headers=self._admin_headers(admin_telegram_user_id),
                params={"days": days},
            )
            response.raise_for_status()
            return response.json()

    async def admin_export(
        self, admin_telegram_user_id: int, days: int = 30
    ) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/admin/export",
                headers=self._admin_headers(admin_telegram_user_id),
                params={"days": days},
            )
            response.raise_for_status()
            return response.text

    async def admin_audit(
        self, admin_telegram_user_id: int, limit: int = 20
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/admin/audit",
                headers=self._admin_headers(admin_telegram_user_id),
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()
