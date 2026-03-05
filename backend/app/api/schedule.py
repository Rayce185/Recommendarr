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

from app.config import settings

router = APIRouter(prefix="/schedule", tags=["schedule"])

# Server timezone (Tautulli reports in server time)
SERVER_TZ = "Europe/Zurich"


def _find_quietest_hour(hourly_plays: list[int], user_tz: str = None) -> dict:
    """Analyze hourly play data to find the optimal refresh time.

    Args:
        hourly_plays: 24-element list, index=hour (server time), value=plays
        user_tz: IANA timezone for the user (to convert suggestion)

    Returns:
        dict with suggested_hour (user-local), analysis data
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime, timezone as tz

    if not hourly_plays or len(hourly_plays) < 24 or sum(hourly_plays) == 0:
        return {"suggested_hour": 4, "suggested_minute": 0, "confidence": "low",
                "reason": "Not enough viewing data — using default 4:00 AM"}

    # Find quietest 2-hour window (wraps around midnight)
    best_start = 0
    best_score = float("inf")
    for h in range(24):
        window = hourly_plays[h] + hourly_plays[(h + 1) % 24]
        if window < best_score:
            best_score = window
            best_start = h

    # Pick the middle of the 2h window, offset by 30min into the quieter hour
    quiet_hour_server = best_start if hourly_plays[best_start] <= hourly_plays[(best_start + 1) % 24] else (best_start + 1) % 24

    # Convert from server time to user's local time
    suggested_hour = quiet_hour_server
    if user_tz and user_tz != SERVER_TZ:
        try:
            server_tz = ZoneInfo(SERVER_TZ)
            target_tz = ZoneInfo(user_tz)
            # Use today's date for DST-aware conversion
            now = datetime.now(tz.utc)
            # Create a datetime at the quiet hour in server time
            server_dt = now.replace(hour=quiet_hour_server, minute=0, second=0, microsecond=0).astimezone(server_tz)
            # Adjust to be actually AT that hour in server tz
            from datetime import timedelta
            offset = server_dt.hour - quiet_hour_server
            server_dt -= timedelta(hours=offset)
            # Convert to user tz
            user_dt = server_dt.astimezone(target_tz)
            suggested_hour = user_dt.hour
        except Exception:
            pass  # Fall back to server hour

    total_plays = sum(hourly_plays)
    confidence = "high" if total_plays >= 50 else "medium" if total_plays >= 20 else "low"
    peak_hour = hourly_plays.index(max(hourly_plays))

    return {
        "suggested_hour": suggested_hour,
        "suggested_minute": 0,
        "confidence": confidence,
        "reason": f"Quietest viewing window based on {total_plays} plays",
        "server_quiet_hour": quiet_hour_server,
        "server_peak_hour": peak_hour,
        "total_plays": total_plays,
        "hourly_plays_server": hourly_plays,
    }


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


@router.get("/{username}/suggest")
async def suggest_schedule(
    username: str,
    user_tz: str = "UTC",
    user: TokenPayload = Depends(get_current_user),
):
    """Suggest optimal refresh time based on Tautulli viewing patterns.

    Analyzes the user's hourly play distribution to find when they're
    least likely to be watching. Converts from server time to user's timezone.
    """
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view other users' schedules")

    # Validate timezone
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(user_tz)
    except Exception:
        raise HTTPException(400, f"Invalid timezone: {user_tz}")

    # Get user's Tautulli ID
    from app.services.factory import get_stack, resolve_user_id
    stack = get_stack()
    uid = resolve_user_id(username)

    # Fetch hourly play data
    try:
        hourly = await stack.tautulli.get_plays_by_hourofday(uid)
    except Exception as e:
        logger.warning(f"Tautulli hourly data failed for {username}: {e}")
        hourly = []

    analysis = _find_quietest_hour(hourly, user_tz)
    analysis["username"] = username
    analysis["timezone"] = user_tz

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
