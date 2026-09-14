"""Pydantic response/request models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    calendar_configured: bool = False


class ScheduleLineOut(BaseModel):
    shift_date: str
    label: str
    status: str


class UploadResponse(BaseModel):
    empty: bool = False
    dry_run: bool = False
    lines: list[ScheduleLineOut] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class ScheduleEventOut(BaseModel):
    summary: str
    date_part: str
    time_part: str | None = None


class ScheduleListResponse(BaseModel):
    events: list[ScheduleEventOut]
    calendar_configured: bool = True


class AckRequest(BaseModel):
    telegram_user_id: int


class AckResponse(BaseModel):
    account_id: int
    streak: int


class StatsResponse(BaseModel):
    account_id: int
    current_streak: int
    longest_streak: int
    adherence_rate: float
    days: int = 30
