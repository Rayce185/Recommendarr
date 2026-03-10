"""Library Health API — vitality scores and sunset zone voting.

User-facing endpoints for viewing vitality, voting on sunset items.
Admin/graveyard/config routes in library_health_admin.py.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.database import get_db
from app.models.library_health import VitalityScore, SunsetItem, SunsetVote

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/library-health", tags=["library-health"])


def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


# ── Vitality ─────────────────────────────────────────────────────

@router.get("/vitality")
async def get_vitality_scores(
    zone: Optional[str] = Query(None, pattern="^(healthy|sunset|dead)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    sort: str = Query("score_asc", pattern="^(score_asc|score_desc|title)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Paginated vitality scores, filterable by zone."""
    db = get_db()
    try:
        q = select(VitalityScore)
        if zone:
            q = q.where(VitalityScore.zone == zone)

        if sort == "score_asc":
            q = q.order_by(VitalityScore.composite_score.asc())
        elif sort == "score_desc":
            q = q.order_by(VitalityScore.composite_score.desc())
        else:
            q = q.order_by(VitalityScore.title.asc())

        count_q = select(VitalityScore.id)
        if zone:
            count_q = count_q.where(VitalityScore.zone == zone)
        total_count = len(db.execute(count_q).all())

        offset = (page - 1) * per_page
        rows = db.execute(q.offset(offset).limit(per_page)).scalars().all()

        return {
            "items": [vitality_to_dict(r) for r in rows],
            "total": total_count,
            "page": page,
            "per_page": per_page,
        }
    finally:
        db.close()


@router.get("/vitality/{tmdb_id}/{media_type}")
async def get_vitality_detail(
    tmdb_id: int, media_type: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Single item vitality detail with signal breakdown."""
    db = get_db()
    try:
        row = db.execute(
            select(VitalityScore).where(
                VitalityScore.tmdb_id == tmdb_id,
                VitalityScore.media_type == media_type,
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Item not found in vitality scores")
        return vitality_to_dict(row)
    finally:
        db.close()


@router.post("/vitality/recalculate")
async def force_recalculate(admin: TokenPayload = Depends(require_admin)):
    """Admin: force immediate vitality recalculation."""
    from app.services.vitality_scheduler import recalculate_vitality
    result = await recalculate_vitality(force=True)
    return result


# ── Sunset Zone ──────────────────────────────────────────────────

@router.get("/sunset")
async def get_sunset_items(user: TokenPayload = Depends(get_current_user)):
    """All items currently in the sunset zone (voting status)."""
    db = get_db()
    try:
        rows = db.execute(
            select(SunsetItem)
            .where(SunsetItem.status == "voting")
            .order_by(SunsetItem.grace_expires_at.asc())
        ).scalars().all()
        return {"items": [sunset_to_dict(r) for r in rows], "count": len(rows)}
    finally:
        db.close()


class VoteRequest(BaseModel):
    vote: str  # keep | kick


@router.post("/sunset/{tmdb_id}/{media_type}/vote")
async def vote_on_item(
    tmdb_id: int, media_type: str, body: VoteRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Cast a keep/kick vote on a sunset zone item."""
    from app.services.sunset_manager import cast_vote
    try:
        result = cast_vote(tmdb_id, media_type, user.plex_user_id, body.vote)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/sunset/{tmdb_id}/{media_type}/votes")
async def get_vote_tally(
    tmdb_id: int, media_type: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Vote tally and individual votes for a sunset item."""
    db = get_db()
    try:
        item = db.execute(
            select(SunsetItem).where(
                SunsetItem.tmdb_id == tmdb_id,
                SunsetItem.media_type == media_type,
            )
        ).scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Sunset item not found")

        votes = db.execute(
            select(SunsetVote).where(
                SunsetVote.tmdb_id == tmdb_id,
                SunsetVote.media_type == media_type,
            )
        ).scalars().all()

        return {
            "tmdb_id": tmdb_id, "media_type": media_type,
            "votes_keep": item.votes_keep, "votes_kick": item.votes_kick,
            "votes": [
                {"user_id": v.user_id, "vote": v.vote,
                 "voted_at": v.voted_at.isoformat() if v.voted_at else None}
                for v in votes
            ],
        }
    finally:
        db.close()


# ── Stats ────────────────────────────────────────────────────────

@router.get("/stats")
async def get_health_stats(user: TokenPayload = Depends(get_current_user)):
    """Dashboard summary: zone counts, kicked count, etc."""
    from sqlalchemy import func as sqlfunc
    from app.models.library_health import KickedItem
    db = get_db()
    try:
        zones = db.execute(
            select(VitalityScore.zone, sqlfunc.count(VitalityScore.id))
            .group_by(VitalityScore.zone)
        ).all()
        zone_counts = {r[0]: r[1] for r in zones}

        kicked_count = db.execute(
            select(sqlfunc.count(KickedItem.id))
            .where(KickedItem.redownloaded_at.is_(None))
        ).scalar() or 0

        voting_count = db.execute(
            select(sqlfunc.count(SunsetItem.id))
            .where(SunsetItem.status == "voting")
        ).scalar() or 0

        pending_count = db.execute(
            select(sqlfunc.count(SunsetItem.id))
            .where(SunsetItem.status == "pending_admin")
        ).scalar() or 0

        return {
            "zones": zone_counts,
            "total_items": sum(zone_counts.values()),
            "items_voting": voting_count,
            "items_pending_admin": pending_count,
            "items_kicked": kicked_count,
        }
    finally:
        db.close()


# ── Serializers ──────────────────────────────────────────────────

def vitality_to_dict(v: VitalityScore) -> dict:
    return {
        "tmdb_id": v.tmdb_id, "media_type": v.media_type,
        "title": v.title, "poster_path": v.poster_path,
        "composite_score": round(v.composite_score, 1),
        "signals": {
            "recency": round(v.recency_score, 1),
            "velocity": round(v.velocity_score, 1),
            "breadth": round(v.breadth_score, 1),
            "rec_frequency": round(v.rec_frequency_score, 1),
            "niche": round(v.niche_score, 1),
        },
        "zone": v.zone,
        "calculated_at": v.calculated_at.isoformat() if v.calculated_at else None,
    }


def sunset_to_dict(s: SunsetItem) -> dict:
    return {
        "tmdb_id": s.tmdb_id, "media_type": s.media_type,
        "title": s.title, "poster_path": s.poster_path,
        "status": s.status, "votes_keep": s.votes_keep, "votes_kick": s.votes_kick,
        "entered_sunset_at": s.entered_sunset_at.isoformat() if s.entered_sunset_at else None,
        "grace_expires_at": s.grace_expires_at.isoformat() if s.grace_expires_at else None,
        "kick_method": s.kick_method,
    }
