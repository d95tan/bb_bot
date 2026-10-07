"""Admin-only FastAPI routes (API key + admin Telegram identity)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from src.api.deps import require_admin_identity, require_api_key
from src.api.schemas import (
    AdminAuditResponse,
    AdminHealthResponse,
    AdminDateRangeRequest,
    AdminDayStatusOut,
    AdminPatchResponse,
    AdminStatsResponse,
    ReminderSendOut,
    ReminderStatusResponse,
    ScheduleEventOut,
    ScheduleListResponse,
    TriggerReminderResponse,
)
from src.app import admin as admin_app
from src.app.admin import AdminError, NoPatientAccountError
from src.config import get_settings

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}: {value}",
        ) from e


def _http_from_admin_error(e: AdminError) -> HTTPException:
    code = (
        status.HTTP_409_CONFLICT
        if isinstance(e, NoPatientAccountError)
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=str(e))


def _patch_response(preview: admin_app.PatchPreview) -> AdminPatchResponse:
    return AdminPatchResponse(
        account_id=preview.account_id,
        start_date=preview.start_date.isoformat(),
        end_date=preview.end_date.isoformat(),
        dates=[d.isoformat() for d in preview.dates],
        already_taken=[d.isoformat() for d in preview.already_taken],
        missing=[d.isoformat() for d in preview.missing],
        applied=[d.isoformat() for d in preview.applied],
        streak_before=preview.streak_before,
        streak_after=preview.streak_after,
        dry_run=preview.dry_run,
        note=preview.note,
    )


def _send_out(send) -> ReminderSendOut:
    sent_at = send.sent_at
    return ReminderSendOut(
        sent_at=sent_at.isoformat(),
        shift_date=send.shift_date.isoformat(),
        reminder_dt=send.reminder_dt.isoformat(),
        source=send.source,
    )


@router.post("/medication/patch", response_model=AdminPatchResponse)
async def patch_medication(
    body: AdminDateRangeRequest,
    actor_id: int = Depends(require_admin_identity),
) -> AdminPatchResponse:
    start = _parse_iso_date(body.start_date, "start_date")
    end = _parse_iso_date(body.end_date, "end_date") if body.end_date else None
    try:
        if body.dry_run:
            preview = admin_app.preview_patch(start, end, note=body.note)
        else:
            preview = admin_app.apply_patch(
                actor_id, start, end, note=body.note
            )
    except AdminError as e:
        raise _http_from_admin_error(e) from e
    return _patch_response(preview)


@router.post("/medication/unlog", response_model=AdminPatchResponse)
async def unlog_medication(
    body: AdminDateRangeRequest,
    actor_id: int = Depends(require_admin_identity),
) -> AdminPatchResponse:
    start = _parse_iso_date(body.start_date, "start_date")
    end = _parse_iso_date(body.end_date, "end_date") if body.end_date else None
    try:
        if body.dry_run:
            preview = admin_app.preview_unlog(start, end, note=body.note)
        else:
            preview = admin_app.apply_unlog(
                actor_id, start, end, note=body.note
            )
    except AdminError as e:
        raise _http_from_admin_error(e) from e
    return _patch_response(preview)


@router.get("/medication/stats", response_model=AdminStatsResponse)
async def admin_medication_stats(
    days: int = Query(default=30, ge=1, le=180),
    actor_id: int = Depends(require_admin_identity),
) -> AdminStatsResponse:
    del actor_id
    try:
        stats = admin_app.get_admin_stats(days=days)
    except AdminError as e:
        raise _http_from_admin_error(e) from e
    return AdminStatsResponse(
        account_id=stats.account_id,
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        adherence_rate=stats.adherence_rate,
        days=stats.days,
        day_by_day=[
            AdminDayStatusOut(date=item.day.isoformat(), taken=item.taken)
            for item in stats.day_by_day
        ],
    )


@router.post("/reminders/trigger", response_model=TriggerReminderResponse)
async def trigger_reminder(
    actor_id: int = Depends(require_admin_identity),
) -> TriggerReminderResponse:
    try:
        result = await admin_app.trigger_reminder_now(actor_id)
    except AdminError as e:
        raise _http_from_admin_error(e) from e
    return TriggerReminderResponse(
        account_id=result.account_id,
        sent=result.sent,
        already_acknowledged=result.already_acknowledged,
        sends=[_send_out(s) for s in result.sends],
    )


@router.get("/reminders/status", response_model=ReminderStatusResponse)
async def reminder_status(
    actor_id: int = Depends(require_admin_identity),
) -> ReminderStatusResponse:
    del actor_id
    try:
        status_ = admin_app.get_reminder_status()
    except AdminError as e:
        raise _http_from_admin_error(e) from e
    return ReminderStatusResponse(
        account_id=status_.account_id,
        timezone=status_.timezone,
        today=status_.today.isoformat(),
        acknowledged=status_.acknowledged,
        sends=[_send_out(s) for s in status_.sends],
    )


@router.get("/health", response_model=AdminHealthResponse)
async def admin_health(
    actor_id: int = Depends(require_admin_identity),
) -> AdminHealthResponse:
    del actor_id
    health = admin_app.get_admin_health()
    return AdminHealthResponse(
        version=health.version,
        calendar_configured=health.calendar_configured,
        data_dir_writable=health.data_dir_writable,
    )


@router.get("/shifts", response_model=ScheduleListResponse)
async def admin_shifts(
    days: int = Query(default=7, ge=1, le=14),
    actor_id: int = Depends(require_admin_identity),
) -> ScheduleListResponse:
    del actor_id
    settings = get_settings()
    if not settings.is_calendar_configured:
        return ScheduleListResponse(events=[], calendar_configured=False)
    try:
        events = await admin_app.get_upcoming_shifts(days=days)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
    return ScheduleListResponse(
        calendar_configured=True,
        events=[
            ScheduleEventOut(
                summary=e.summary,
                date_part=e.date_part,
                time_part=e.time_part,
            )
            for e in events
        ],
    )


@router.get("/export")
async def admin_export(
    days: int = Query(default=30, ge=1, le=180),
    actor_id: int = Depends(require_admin_identity),
) -> PlainTextResponse:
    del actor_id
    try:
        csv_body = admin_app.export_taken_csv(days=days)
    except AdminError as e:
        raise _http_from_admin_error(e) from e
    return PlainTextResponse(csv_body, media_type="text/csv")


@router.get("/audit", response_model=AdminAuditResponse)
async def admin_audit(
    limit: int = Query(default=20, ge=1, le=100),
    actor_id: int = Depends(require_admin_identity),
) -> AdminAuditResponse:
    del actor_id
    page = admin_app.get_audit(limit=limit)
    return AdminAuditResponse(entries=page.entries)
