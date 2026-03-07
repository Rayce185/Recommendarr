"""Recommendation History — log, query, and manage recommendation history.

Populates RecommendationLog on each recommendation cycle.
Provides per-user history queries and "don't recommend again" exclusion.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RecommendationLog, User, TmdbCache

logger = logging.getLogger(__name__)


def _resolve_user_db_id(db: Session, username: str) -> Optional[int]:
    """Get or create internal user ID from username.

    Auto-creates a User row if one doesn't exist yet (since the app
    uses Tautulli as user source of truth, the DB may not have all users).
    """
    row = db.execute(
        select(User.id).where(User.username == username)
    ).scalar_one_or_none()
    if row is not None:
        return row

    # Auto-create user record
    try:
        new_user = User(
            plex_user_id=abs(hash(username)) % 2147483647,  # Unique placeholder
            username=username,
            display_name=username,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"rec_history: auto-created user '{username}' (id={new_user.id})")
        return new_user.id
    except Exception as e:
        db.rollback()
        logger.warning(f"rec_history: failed to create user '{username}': {e}")
        return None


def log_recommendations(
    username: str,
    recommendations: list,
    mode: str,
) -> int:
    """Log a batch of recommendations for a user.

    Args:
        username: Plex username
        recommendations: List of Recommendation objects from engine
        mode: Recommendation mode (tonight, grab, rediscover, mood, group)

    Returns:
        Number of entries logged
    """
    if not recommendations:
        return 0

    try:
        db = get_db()
        user_id = _resolve_user_db_id(db, username)
        if user_id is None:
            logger.warning(f"rec_history: user '{username}' not found in DB, skipping log")
            db.close()
            return 0

        count = 0
        for rec in recommendations:
            entry = RecommendationLog(
                user_id=user_id,
                tmdb_id=rec.tmdb_id,
                media_type=getattr(rec, 'media_type', 'movie'),
                mode=mode,
                score=round(rec.score, 4) if rec.score else None,
                explanation=getattr(rec, 'explanation', None),
                signals=getattr(rec, 'score_breakdown', None),
                influenced_by=getattr(rec, 'explanation_signals', None),
            )
            db.add(entry)
            count += 1

        db.commit()
        db.close()
        logger.info(f"rec_history: logged {count} recs for {username} (mode={mode})")
        return count
    except Exception as e:
        logger.error(f"rec_history: failed to log: {e}")
        return 0


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
            poster = f"https://image.tmdb.org/t/p/w342{tmdb.poster_path}" if not tmdb.poster_path.startswith("http") else tmdb.poster_path
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


def mark_interaction(
    username: str,
    tmdb_id: int,
    interaction: str,
) -> bool:
    """Mark a recommendation as clicked/watched/requested.

    Args:
        interaction: One of 'clicked', 'watched', 'requested'
    """
    field_map = {
        "clicked": "was_clicked",
        "watched": "was_watched",
        "requested": "was_requested",
    }
    if interaction not in field_map:
        return False

    db = get_db()
    user_id = _resolve_user_db_id(db, username)
    if user_id is None:
        db.close()
        return False

    # Update most recent log entry for this user+tmdb_id
    row = db.execute(
        select(RecommendationLog)
        .where(and_(
            RecommendationLog.user_id == user_id,
            RecommendationLog.tmdb_id == tmdb_id,
        ))
        .order_by(desc(RecommendationLog.created_at))
        .limit(1)
    ).scalar_one_or_none()

    if row:
        setattr(row, field_map[interaction], True)
        db.commit()
        db.close()
        return True

    db.close()
    return False


def get_recent_rec_map(username: str, days: int = 30) -> dict[int, dict]:
    """Get recently recommended items with recency info for freshness scoring.

    Returns {tmdb_id: {"count": N, "last_at": datetime, "hours_ago": float}}.
    """
    try:
        db = get_db()
        user_id = _resolve_user_db_id(db, username)
        if not user_id:
            db.close()
            return {}

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = db.execute(
            select(
                RecommendationLog.tmdb_id,
                func.count().label("cnt"),
                func.max(RecommendationLog.created_at).label("last_at"),
            )
            .where(and_(
                RecommendationLog.user_id == user_id,
                RecommendationLog.created_at >= cutoff,
            ))
            .group_by(RecommendationLog.tmdb_id)
        ).all()

        now = datetime.now(timezone.utc)
        result = {}
        for tmdb_id, cnt, last_at in rows:
            # SQLite stores naive datetimes — make timezone-aware for comparison
            if last_at and last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            hours = (now - last_at).total_seconds() / 3600 if last_at else 999
            result[tmdb_id] = {"count": cnt, "last_at": last_at, "hours_ago": hours}

        db.close()
        return result
    except Exception as e:
        logger.warning(f"get_recent_rec_map failed: {e}")
        return {}
