"""Medication acknowledgment and stats routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import require_api_key
from src.api.schemas import AckRequest, AckResponse, StatsResponse
from src.app import medication as medication_app
from src.services.accounts import resolve_telegram_account

router = APIRouter(
    prefix="/medication",
    tags=["medication"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/ack", response_model=AckResponse)
async def ack_medication(body: AckRequest) -> AckResponse:
    account_id = resolve_telegram_account(body.telegram_user_id)
    if account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized telegram user",
        )
    result = medication_app.acknowledge_medication(account_id)
    return AckResponse(account_id=result.account_id, streak=result.streak)


@router.get("/stats", response_model=StatsResponse)
async def medication_stats(
    telegram_user_id: int = Query(...),
    days: int = Query(default=30, ge=1, le=365),
) -> StatsResponse:
    account_id = resolve_telegram_account(telegram_user_id)
    if account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized telegram user",
        )
    stats = medication_app.get_medication_stats(account_id, days=days)
    return StatsResponse(
        account_id=stats.account_id,
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        adherence_rate=stats.adherence_rate,
        days=stats.days,
    )
