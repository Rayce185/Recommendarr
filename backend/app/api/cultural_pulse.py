"""Cultural Pulse API — manage RSS sources, trigger refresh, get active themes."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.cultural_pulse import (
    refresh_pulse, get_active_events, get_all_sources,
)
from app.database import get_db
from app.models import PulseSource, ZeitgeistEvent, ZeitgeistMapping
from sqlalchemy import select


def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


router = APIRouter(prefix="/pulse", tags=["Cultural Pulse"])


@router.get("/themes")
async def get_pulse_themes(
    limit: int = 10,
    user: TokenPayload = Depends(get_current_user),
):
    """Get active cultural pulse themes with their recommendation mappings."""
    events = get_active_events(limit=limit)
    return {"themes": events, "count": len(events)}


@router.post("/refresh")
async def trigger_pulse_refresh(
    admin: TokenPayload = Depends(require_admin),
):
    """Manually trigger a pulse refresh cycle (admin only).

    Fetches due RSS sources, extracts themes via LLM, persists new events.
    """
    try:
        created = await refresh_pulse()
        return {
            "status": "ok",
            "created": len(created),
            "events": created,
            "message": f"Pulse refresh complete. {len(created)} new themes detected.",
        }
    except Exception as e:
        raise HTTPException(500, f"Pulse refresh failed: {str(e)[:300]}")


@router.get("/sources")
async def list_pulse_sources(
    admin: TokenPayload = Depends(require_admin),
):
    """List all configured RSS pulse sources."""
    sources = get_all_sources()
    return {"sources": sources, "count": len(sources)}


class AddSourceRequest(BaseModel):
    source_name: str
    source_url: str
    category: str = "film_news"
    check_interval_hours: int = 24


@router.post("/sources")
async def add_pulse_source(
    body: AddSourceRequest,
    admin: TokenPayload = Depends(require_admin),
):
    """Add a new RSS source for cultural pulse."""
    with get_db() as db:
        existing = db.execute(
            select(PulseSource).where(PulseSource.source_url == body.source_url)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(409, f"Source URL already exists (id={existing.id})")

        src = PulseSource(
            source_type="rss",
            source_name=body.source_name,
            source_url=body.source_url,
            category=body.category,
            is_enabled=True,
            check_interval_hours=body.check_interval_hours,
        )
        db.add(src)
        db.commit()
        return {"status": "ok", "id": src.id, "message": f"Added source: {src.source_name}"}


class UpdateSourceRequest(BaseModel):
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    category: Optional[str] = None
    is_enabled: Optional[bool] = None
    check_interval_hours: Optional[int] = None


@router.put("/sources/{source_id}")
async def update_pulse_source(
    source_id: int,
    body: UpdateSourceRequest,
    admin: TokenPayload = Depends(require_admin),
):
    """Update an existing RSS source."""
    with get_db() as db:
        src = db.get(PulseSource, source_id)
        if not src:
            raise HTTPException(404, "Source not found")
        if body.source_name is not None:
            src.source_name = body.source_name
        if body.source_url is not None:
            src.source_url = body.source_url
        if body.category is not None:
            src.category = body.category
        if body.is_enabled is not None:
            src.is_enabled = body.is_enabled
        if body.check_interval_hours is not None:
            src.check_interval_hours = body.check_interval_hours
        db.commit()
        return {"status": "ok", "message": f"Updated source: {src.source_name}"}


@router.delete("/sources/{source_id}")
async def delete_pulse_source(
    source_id: int,
    admin: TokenPayload = Depends(require_admin),
):
    """Delete an RSS source."""
    with get_db() as db:
        src = db.get(PulseSource, source_id)
        if not src:
            raise HTTPException(404, "Source not found")
        db.delete(src)
        db.commit()
        return {"status": "ok", "message": f"Deleted source: {src.source_name}"}


@router.delete("/themes/{event_id}")
async def deactivate_theme(
    event_id: int,
    admin: TokenPayload = Depends(require_admin),
):
    """Deactivate a pulse theme (soft delete)."""
    with get_db() as db:
        event = db.get(ZeitgeistEvent, event_id)
        if not event:
            raise HTTPException(404, "Theme not found")
        event.is_active = False
        db.commit()
        return {"status": "ok", "message": f"Deactivated theme: {event.title}"}
