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


class AdminDateRangeRequest(BaseModel):
    start_date: str
    end_date: str | None = None
    note: str | None = Field(default=None, max_length=200)
    dry_run: bool = False


class AdminPatchResponse(BaseModel):
    account_id: int
    start_date: str
    end_date: str
    dates: list[str]
    already_taken: list[str]
    missing: list[str]
    applied: list[str]
    streak_before: int
    streak_after: int
    dry_run: bool
    note: str | None = None


class AdminDayStatusOut(BaseModel):
    date: str
    taken: bool


class AdminStatsResponse(BaseModel):
    account_id: int
    current_streak: int
    longest_streak: int
    adherence_rate: float
    days: int
    day_by_day: list[AdminDayStatusOut]


class ReminderSendOut(BaseModel):
    sent_at: str
    shift_date: str
    reminder_dt: str
    source: str


class ReminderStatusResponse(BaseModel):
    account_id: int
    timezone: str
    today: str
    acknowledged: bool
    sends: list[ReminderSendOut]


class TriggerReminderResponse(BaseModel):
    account_id: int
    sent: int
    already_acknowledged: bool
    sends: list[ReminderSendOut]


class AdminHealthResponse(BaseModel):
    version: str
    calendar_configured: bool
    data_dir_writable: bool


class AdminAuditResponse(BaseModel):
    entries: list[dict] = Field(default_factory=list)
