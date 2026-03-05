"""Scheduled refresh API — per-user timezone-aware auto-refresh config."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.database import get_db
from app.models.tables import RefreshSchedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    timezone: Optional[str] = Field(None, max_length=60)
    hour: Optional[int] = Field(None, ge=0, le=23)
    minute: Optional[int] = Field(None, ge=0, le=59)


class ScheduleResponse(BaseModel):
    username: str
    enabled: bool
    timezone: str
    hour: int
    minute: int
    last_run_at: Optional[str] = None
    last_run_ms: Optional[int] = None
    last_error: Optional[str] = None


def _sched_to_response(sched: RefreshSchedule) -> dict:
    return {
        "username": sched.username,
        "enabled": sched.enabled,
        "timezone": sched.timezone,
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
            "timezone": "UTC",
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

    # Validate timezone
    if body.timezone:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(body.timezone)
        except Exception:
            raise HTTPException(400, f"Invalid timezone: {body.timezone}")

    with get_db() as db:
        sched = db.execute(
            select(RefreshSchedule).where(RefreshSchedule.username == username)
        ).scalar_one_or_none()

        if not sched:
            sched = RefreshSchedule(
                username=username,
                enabled=body.enabled if body.enabled is not None else False,
                timezone=body.timezone or "UTC",
                hour=body.hour if body.hour is not None else 4,
                minute=body.minute if body.minute is not None else 0,
            )
            db.add(sched)
        else:
            if body.enabled is not None:
                sched.enabled = body.enabled
            if body.timezone is not None:
                sched.timezone = body.timezone
            if body.hour is not None:
                sched.hour = body.hour
            if body.minute is not None:
                sched.minute = body.minute
            sched.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(sched)
        result = _sched_to_response(sched)

    action = "enabled" if result["enabled"] else "disabled"
    logger.info(f"Schedule {action} for {username}: {result['hour']:02d}:{result['minute']:02d} {result['timezone']}")
    return result


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
