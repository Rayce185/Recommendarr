"""Recommendation History — log, write, and interaction tracking.

Core write operations: logging recommendations, marking interactions,
and querying recent recommendation maps for freshness scoring.

Query/read operations split to rec_history_queries.py per §7.7.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RecommendationLog, User

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
