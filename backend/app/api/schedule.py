"""Scheduled refresh API — per-user timezone-aware auto-refresh config."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.database import get_db
from app.models import RefreshSchedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])



def _find_quietest_hour(hourly_plays: list[int]) -> dict:
    """Find the quietest hour from Tautulli hourly play data.

    Tautulli reports in server time. Server runs the scheduler in server time.
    No timezone conversion needed — the data already reflects when the user
    is actually inactive because their viewing patterns encode their timezone.

    Args:
        hourly_plays: 24-element list, index=hour, value=play count

    Returns:
        dict with suggested_hour (server time), confidence, analysis
    """
    if not hourly_plays or len(hourly_plays) < 24 or sum(hourly_plays) == 0:
        return {"suggested_hour": 4, "suggested_minute": 0, "confidence": "low",
                "reason": "Not enough viewing data — using default 4:00"}

    # Find quietest 2-hour window (wraps around midnight)
    best_start = 0
    best_score = float("inf")
    for h in range(24):
        window = hourly_plays[h] + hourly_plays[(h + 1) % 24]
        if window < best_score:
            best_score = window
            best_start = h

    # Pick the quieter of the two hours in the window
    quiet_hour = best_start if hourly_plays[best_start] <= hourly_plays[(best_start + 1) % 24] else (best_start + 1) % 24

    total_plays = sum(hourly_plays)
    confidence = "high" if total_plays >= 50 else "medium" if total_plays >= 20 else "low"
    peak_hour = hourly_plays.index(max(hourly_plays))

    return {
        "suggested_hour": quiet_hour,
        "suggested_minute": 0,
        "confidence": confidence,
        "reason": f"Quietest viewing window based on {total_plays} plays",
        "peak_hour": peak_hour,
        "total_plays": total_plays,
        "hourly_plays": hourly_plays,
    }


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    minute: Optional[int] = Field(None, ge=0, le=59)


class ScheduleResponse(BaseModel):
    username: str
    enabled: bool
    hour: int
    minute: int
    last_run_at: Optional[str] = None
    last_run_ms: Optional[int] = None
    last_error: Optional[str] = None


def _sched_to_response(sched: RefreshSchedule) -> dict:
    return {
        "username": sched.username,
        "enabled": sched.enabled,
        "hour": sched.hour,
        "minute": sched.minute,
        "last_run_at": sched.last_run_at.isoformat() if sched.last_run_at else None,
        "last_run_ms": sched.last_run_ms,
        "last_error": sched.last_error,
    }


@router.get("/{username}")
async def get_schedule(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Get a user's refresh schedule. Returns defaults if none configured."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view other users' schedules")

    with get_db() as db:
        sched = db.execute(
            select(RefreshSchedule).where(RefreshSchedule.username == username)
        ).scalar_one_or_none()

    if not sched:
        # Return defaults (not persisted yet)
        return {
            "username": username,
            "enabled": False,
            "hour": 4,
            "minute": 0,
            "last_run_at": None,
            "last_run_ms": None,
            "last_error": None,
        }

    return _sched_to_response(sched)


@router.put("/{username}")
async def update_schedule(
    username: str,
    body: ScheduleUpdate,
    user: TokenPayload = Depends(get_current_user),
):
    """Create or update a user's refresh schedule."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot modify other users' schedules")

    with get_db() as db:
        sched = db.execute(
            select(RefreshSchedule).where(RefreshSchedule.username == username)
        ).scalar_one_or_none()

        if not sched:
            sched = RefreshSchedule(
                username=username,
                enabled=body.enabled if body.enabled is not None else False,
                hour=body.hour if body.hour is not None else 4,
                minute=body.minute if body.minute is not None else 0,
            )
            db.add(sched)
        else:
            if body.enabled is not None:
                sched.enabled = body.enabled
            if body.hour is not None:
                sched.hour = body.hour
            if body.minute is not None:
                sched.minute = body.minute
            sched.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(sched)
        result = _sched_to_response(sched)

    action = "enabled" if result["enabled"] else "disabled"
    logger.info(f"Schedule {action} for {username}: {result['hour']:02d}:{result['minute']:02d} server time")
    return result


@router.get("/{username}/suggest")
async def suggest_schedule(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Suggest optimal refresh time based on Tautulli viewing patterns.

    Analyzes per-user hourly play distribution to find their quietest hour.
    All times are server time — no timezone conversion needed because
    Tautulli data already reflects when the user is actually inactive.
    """
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view other users' schedules")

    from app.services.factory import get_stack, resolve_user_id
    stack = get_stack()
    uid = resolve_user_id(username)

    try:
        hourly = await stack.tautulli.get_plays_by_hourofday(uid)
    except Exception as e:
        logger.warning(f"Tautulli hourly data failed for {username}: {e}")
        hourly = []

    analysis = _find_quietest_hour(hourly)
    analysis["username"] = username

    return analysis


@router.get("")
async def list_schedules(
    user: TokenPayload = Depends(get_current_user),
):
    """List all configured schedules (admin only)."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")

    with get_db() as db:
        schedules = db.execute(select(RefreshSchedule)).scalars().all()

    return {
        "schedules": [_sched_to_response(s) for s in schedules],
        "total": len(schedules),
    }
