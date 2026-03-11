"""Library Health Admin API — graveyard, admin actions, config.

Admin-facing endpoints for kick confirmation, graveyard management,
re-download, and Kick-Vote configuration.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select, desc

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.database import get_db
from app.models.library_health import SunsetItem, KickedItem
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/library-health", tags=["library-health"])


def _require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


# ── Admin Actions ────────────────────────────────────────────────

@router.get("/pending")
async def get_pending_kicks(admin: TokenPayload = Depends(_require_admin)):
    """Items awaiting admin confirmation."""
    from app.api.library_health import sunset_to_dict
    db = get_db()
    try:
        rows = db.execute(
            select(SunsetItem).where(SunsetItem.status == "pending_admin")
        ).scalars().all()
        return {"items": [sunset_to_dict(r) for r in rows], "count": len(rows)}
    finally:
        db.close()


@router.post("/pending/{tmdb_id}/{media_type}/confirm")
async def confirm_kick(
    tmdb_id: int, media_type: str,
    admin: TokenPayload = Depends(_require_admin),
):
    """Admin confirms a pending kick → executes deletion."""
    from app.services.sunset_manager import admin_confirm_kick
    from app.services.kick_executor import execute_kick
    try:
        admin_confirm_kick(tmdb_id, media_type)
        result = await execute_kick(tmdb_id, media_type)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/pending/{tmdb_id}/{media_type}/veto")
async def veto_kick(
    tmdb_id: int, media_type: str,
    admin: TokenPayload = Depends(_require_admin),
):
    """Admin vetoes a pending kick → reprieve with immunity."""
    from app.services.sunset_manager import admin_veto_kick
    try:
        item = admin_veto_kick(tmdb_id, media_type)
        return {"status": "reprieved", "immune_until": item.immune_until.isoformat()}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Graveyard ────────────────────────────────────────────────────

@router.get("/graveyard")
async def get_graveyard(user: TokenPayload = Depends(get_current_user)):
    """All kicked items available for re-download."""
    db = get_db()
    try:
        rows = db.execute(
            select(KickedItem)
            .where(KickedItem.redownloaded_at.is_(None))
            .order_by(desc(KickedItem.kicked_at))
        ).scalars().all()
        return {"items": [_kicked_to_dict(r) for r in rows], "count": len(rows)}
    finally:
        db.close()


@router.post("/graveyard/{item_id}/redownload")
async def redownload_item(
    item_id: int,
    admin: TokenPayload = Depends(_require_admin),
):
    """Re-add a kicked item to Radarr/Sonarr with original parameters."""
    from app.services.factory import get_stack
    from datetime import datetime, timezone

    db = get_db()
    try:
        kicked = db.execute(
            select(KickedItem).where(KickedItem.id == item_id)
        ).scalar_one_or_none()
        if not kicked:
            raise HTTPException(404, "Kicked item not found")
        if kicked.redownloaded_at:
            raise HTTPException(400, "Already re-downloaded")

        stack = get_stack()
        if kicked.servarr_type == "radarr":
            client = stack.registry.get_default_for("movie")
            if not client:
                raise HTTPException(500, "No Radarr instance configured")
            await client.add_movie(
                tmdb_id=kicked.tmdb_id,
                quality_profile_id=kicked.quality_profile_id or 1,
                root_folder=kicked.root_folder or "/movies",
                tags=kicked.tags or [],
            )
        else:
            raise HTTPException(501, "Sonarr re-download not yet implemented")

        kicked.redownloaded_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "redownloaded", "title": kicked.title, "tmdb_id": kicked.tmdb_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Re-download failed: {e}")
    finally:
        db.close()


@router.post("/graveyard/{item_id}/check-availability")
@limiter.limit("5/minute")
async def check_availability(
    request: Request, item_id: int,
    user: TokenPayload = Depends(get_current_user),
):
    """Live indexer probe for re-download availability."""
    from app.services.redownload_eta import probe_indexer_availability

    db = get_db()
    try:
        kicked = db.execute(
            select(KickedItem).where(KickedItem.id == item_id)
        ).scalar_one_or_none()
        if not kicked:
            raise HTTPException(404, "Kicked item not found")
        return await probe_indexer_availability(kicked.tmdb_id, kicked.media_type)
    finally:
        db.close()


# ── Config ───────────────────────────────────────────────────────

@router.get("/config")
async def get_health_config(admin: TokenPayload = Depends(_require_admin)):
    """Current Kick-Vote configuration (flat keys for frontend)."""
    from app.services.vitality_scoring import DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS
    from app.models.admin import AppSetting
    db = get_db()
    try:
        row = db.execute(
            select(AppSetting).where(AppSetting.key == "kick_vote_config")
        ).scalar_one_or_none()
        if row and row.value:
            cfg = json.loads(row.value) if isinstance(row.value, str) else row.value
        else:
            cfg = {"weights": DEFAULT_WEIGHTS, "thresholds": DEFAULT_THRESHOLDS}

        # Flatten nested → flat keys for frontend compatibility
        w = cfg.get("weights", DEFAULT_WEIGHTS)
        t = cfg.get("thresholds", DEFAULT_THRESHOLDS)
        return {
            "weight_recency": w.get("recency", 0.3),
            "weight_velocity": w.get("velocity", 0.25),
            "weight_breadth": w.get("breadth", 0.2),
            "weight_rec_freq": w.get("rec_frequency", 0.1),
            "weight_niche": w.get("niche", 0.15),
            "threshold_healthy": t.get("healthy_min", 40),
            "threshold_dead": t.get("sunset_min", 15),
            "grace_period_days": t.get("grace_period_days", 7),
            "vote_quorum": t.get("vote_quorum", 3),
        }
    finally:
        db.close()


@router.put("/config")
async def update_health_config(
    config: dict, admin: TokenPayload = Depends(_require_admin),
):
    """Update Kick-Vote configuration (flat keys → nested storage)."""
    from app.models.admin import AppSetting
    # Convert flat frontend keys to nested storage format
    nested = {
        "weights": {
            "recency": config.get("weight_recency", 0.3),
            "velocity": config.get("weight_velocity", 0.25),
            "breadth": config.get("weight_breadth", 0.2),
            "rec_frequency": config.get("weight_rec_freq", 0.1),
            "niche": config.get("weight_niche", 0.15),
        },
        "thresholds": {
            "healthy_min": config.get("threshold_healthy", 40),
            "sunset_min": config.get("threshold_dead", 15),
            "grace_period_days": config.get("grace_period_days", 7),
            "vote_kick_pct": 0.6,
            "vote_quorum": config.get("vote_quorum", 3),
            "reprieve_immunity_days": 30,
            "active_user_days": 90,
        },
    }
    db = get_db()
    try:
        row = db.execute(
            select(AppSetting).where(AppSetting.key == "kick_vote_config")
        ).scalar_one_or_none()
        if row:
            row.value = json.dumps(nested)
        else:
            db.add(AppSetting(key="kick_vote_config", value=json.dumps(nested)))
        db.commit()
        return {"status": "updated"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Serializers ──────────────────────────────────────────────────

def _kicked_to_dict(k: KickedItem) -> dict:
    return {
        "id": k.id, "tmdb_id": k.tmdb_id, "media_type": k.media_type,
        "title": k.title, "poster_url": k.poster_path,
        "year": k.year, "genres": k.genres, "overview": k.overview,
        "vitality_at_kick": round(k.vitality_at_kick, 1) if k.vitality_at_kick else None,
        "kicked_at": k.kicked_at.isoformat() if k.kicked_at else None,
        "kicked_by": k.kicked_by,
        "redownload_eta": k.redownload_eta_tier,
        "servarr_type": k.servarr_type,
    }
