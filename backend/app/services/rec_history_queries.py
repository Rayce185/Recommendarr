"""Recommendation History — query and statistics functions.

Read-only operations for recommendation history: paginated queries,
stats aggregation, and TMDB metadata enrichment.

Split from rec_history.py per §7.7 (300-line limit).
"""

import logging
from typing import Optional

from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RecommendationLog, TmdbCache
from app.services.rec_history import _resolve_user_db_id

logger = logging.getLogger(__name__)


def get_history(
    username: str,
    limit: int = 50,
    offset: int = 0,
    mode: Optional[str] = None,
    media_type: Optional[str] = None,
) -> dict:
    """Get recommendation history for a user.

    Returns dict with 'items' list and 'total' count for pagination.
    """
    db = get_db()
    user_id = _resolve_user_db_id(db, username)
    if user_id is None:
        db.close()
        return {"items": [], "total": 0}

    filters = [RecommendationLog.user_id == user_id]
    if mode:
        filters.append(RecommendationLog.mode == mode)
    if media_type:
        filters.append(RecommendationLog.media_type == media_type)

    # Total count
    total = db.execute(
        select(func.count(RecommendationLog.id)).where(and_(*filters))
    ).scalar() or 0

    # Fetch items
    rows = db.execute(
        select(RecommendationLog)
        .where(and_(*filters))
        .order_by(desc(RecommendationLog.created_at))
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    # Batch-fetch TMDB metadata for enrichment
    tmdb_ids = [(r.tmdb_id, r.media_type or "movie") for r in rows]
    tmdb_map = {}
    if tmdb_ids:
        cache_rows = db.execute(
            select(TmdbCache).where(
                TmdbCache.tmdb_id.in_([t[0] for t in tmdb_ids])
            )
        ).scalars().all()
        for cr in cache_rows:
            tmdb_map[(cr.tmdb_id, cr.media_type)] = cr

    items = []
    for r in rows:
        tmdb = tmdb_map.get((r.tmdb_id, r.media_type or "movie"))
        poster = None
        if tmdb and tmdb.poster_path:
            poster = (
                f"https://image.tmdb.org/t/p/w342{tmdb.poster_path}"
                if not tmdb.poster_path.startswith("http")
                else tmdb.poster_path
            )
        items.append({
            "id": r.id,
            "tmdb_id": r.tmdb_id,
            "media_type": r.media_type,
            "mode": r.mode,
            "score": float(r.score) if r.score else None,
            "explanation": r.explanation,
            "was_clicked": r.was_clicked,
            "was_watched": r.was_watched,
            "was_requested": r.was_requested,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "title": tmdb.title if tmdb else None,
            "year": tmdb.year if tmdb else None,
            "poster_url": poster,
            "vote_average": float(tmdb.vote_average) if tmdb and tmdb.vote_average else None,
            "genres": tmdb.genres if tmdb else None,
            "overview": tmdb.overview if tmdb else None,
        })

    db.close()
    return {"items": items, "total": total}


def get_history_stats(username: str) -> dict:
    """Get aggregate stats for user's recommendation history."""
    db = get_db()
    user_id = _resolve_user_db_id(db, username)
    if user_id is None:
        db.close()
        return {"total": 0, "by_mode": {}, "unique_titles": 0}

    base = RecommendationLog.user_id == user_id

    total = db.execute(
        select(func.count(RecommendationLog.id)).where(base)
    ).scalar() or 0

    unique = db.execute(
        select(func.count(func.distinct(RecommendationLog.tmdb_id))).where(base)
    ).scalar() or 0

    # Count by mode
    mode_rows = db.execute(
        select(RecommendationLog.mode, func.count(RecommendationLog.id))
        .where(base)
        .group_by(RecommendationLog.mode)
    ).all()
    by_mode = {row[0]: row[1] for row in mode_rows if row[0]}

    watched = db.execute(
        select(func.count(RecommendationLog.id))
        .where(and_(base, RecommendationLog.was_watched == True))
    ).scalar() or 0

    requested = db.execute(
        select(func.count(RecommendationLog.id))
        .where(and_(base, RecommendationLog.was_requested == True))
    ).scalar() or 0

    db.close()
    return {
        "total": total,
        "unique_titles": unique,
        "by_mode": by_mode,
        "watched": watched,
        "requested": requested,
    }
