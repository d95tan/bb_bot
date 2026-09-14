"""Schedule upload and listing routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from src.api.deps import require_api_key
from src.api.schemas import (
    ScheduleEventOut,
    ScheduleLineOut,
    ScheduleListResponse,
    UploadResponse,
)
from src.app import schedules as schedules_app
from src.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/schedules",
    tags=["schedules"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/upload", response_model=UploadResponse)
async def upload_schedule(file: UploadFile = File(...)) -> UploadResponse:
    settings = get_settings()
    if not settings.is_calendar_configured and settings.enable_calendar_upload:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar is not configured",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty image upload",
        )

    try:
        result = await schedules_app.upload_schedule_image(image_bytes)
    except Exception as e:
        logger.exception("Schedule upload failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e

    return UploadResponse(
        empty=result.empty,
        dry_run=result.dry_run,
        lines=[
            ScheduleLineOut(
                shift_date=line.shift_date.isoformat(),
                label=line.label,
                status=line.status,
            )
            for line in result.lines
        ],
        stats=result.stats,
    )


@router.get("", response_model=ScheduleListResponse)
async def list_schedules(
    weeks: int = Query(default=4, ge=1, le=12),
) -> ScheduleListResponse:
    settings = get_settings()
    if not settings.is_calendar_configured:
        return ScheduleListResponse(events=[], calendar_configured=False)

    try:
        events = await schedules_app.get_upcoming_schedule(weeks=weeks)
    except Exception as e:
        logger.exception("Schedule list failed: %s", e)
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
