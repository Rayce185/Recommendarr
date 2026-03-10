"""Vitality scheduler — daily recalculation of all library item scores.

Aggregates play data from WatchHistory + RecommendationLog, computes
signals via vitality_scoring, persists to VitalityScore table, and
triggers sunset zone transitions via sunset_manager.
"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy import select, func as sqlfunc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.core import WatchHistory, RecommendationLog, User
from app.models.library_health import VitalityScore, SunsetItem
from app.services.vitality_scoring import (
    VitalitySignals, PlayStats, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS,
    score_recency, score_velocity, score_breadth,
    score_rec_frequency, score_niche, compute_vitality,
    estimate_redownload_tier,
)

logger = logging.getLogger(__name__)


def _load_config(db: Session) -> tuple[dict, dict]:
    """Load admin-configured weights/thresholds from AppSetting, or use defaults."""
    from app.models.admin import AppSetting
    weights = dict(DEFAULT_WEIGHTS)
    thresholds = dict(DEFAULT_THRESHOLDS)
    try:
        row = db.execute(
            select(AppSetting).where(AppSetting.key == "kick_vote_config")
        ).scalar_one_or_none()
        if row and row.value:
            import json
            cfg = json.loads(row.value) if isinstance(row.value, str) else row.value
            weights.update(cfg.get("weights", {}))
            thresholds.update(cfg.get("thresholds", {}))
    except Exception:
        pass  # use defaults
    return weights, thresholds


def _get_active_user_count(db: Session, days: int) -> int:
    """Count users who have watched something within the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = db.execute(
        select(sqlfunc.count(sqlfunc.distinct(WatchHistory.user_id)))
        .where(WatchHistory.created_at >= cutoff)
    ).scalar()
    return result or 1  # floor of 1 to avoid division by zero


def _aggregate_play_stats(db: Session) -> dict[tuple[int, str], PlayStats]:
    """Build per-item play statistics from WatchHistory."""
    now = datetime.now(timezone.utc)
    six_months_ago = now - timedelta(days=180)

    rows = db.execute(
        select(WatchHistory).where(WatchHistory.created_at >= six_months_ago)
    ).scalars().all()

    stats: dict[tuple[int, str], PlayStats] = {}
    for r in rows:
        key = (r.tmdb_id, r.media_type)
        if key not in stats:
            stats[key] = PlayStats(tmdb_id=r.tmdb_id, media_type=r.media_type)
        s = stats[key]
        s.total_plays += r.watch_count or 1
        if r.user_id:
            s.unique_users.add(r.user_id)
        ts = r.created_at or r.started_at
        if ts:
            if s.last_played is None or ts > s.last_played:
                s.last_played = ts

    # Build monthly play buckets (index 0 = most recent month)
    for s in stats.values():
        s.monthly_plays = [0] * 6
        # Re-scan the relevant rows for this item to bucket by month
    # More efficient: bucket during initial scan
    month_data: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0] * 6)
    for r in rows:
        key = (r.tmdb_id, r.media_type)
        ts = r.created_at or r.started_at
        if ts:
            months_ago = max(0, min(5, (now - ts).days // 30))
            month_data[key][months_ago] += r.watch_count or 1

    for key, months in month_data.items():
        if key in stats:
            stats[key].monthly_plays = months

    return stats


def _get_rec_frequency(db: Session) -> dict[tuple[int, str], int]:
    """Count recommendation appearances per item in last 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.execute(
        select(
            RecommendationLog.tmdb_id,
            RecommendationLog.media_type,
            sqlfunc.count(RecommendationLog.id),
        )
        .where(RecommendationLog.created_at >= cutoff)
        .group_by(RecommendationLog.tmdb_id, RecommendationLog.media_type)
    ).all()
    return {(r[0], r[1] or "movie"): r[2] for r in rows}


def _get_genre_distribution(library_items: list[dict]) -> tuple[dict[str, int], int]:
    """Compute genre frequency across the library for niche scoring."""
    genre_counts: dict[str, int] = defaultdict(int)
    total = len(library_items)
    for item in library_items:
        for g in item.get("genres", []):
            name = g if isinstance(g, str) else g.get("name", "")
            if name:
                genre_counts[name.lower()] += 1
    return dict(genre_counts), total


async def recalculate_vitality(force: bool = False) -> dict:
    """Full vitality recalculation for the entire library.

    1. Load all Radarr+Sonarr library items
    2. Aggregate play stats from WatchHistory
    3. Score each item
    4. Persist to VitalityScore table
    5. Trigger sunset transitions

    Returns summary stats.
    """
    from app.services.factory import get_stack

    stack = get_stack()
    db = get_db()
    now = datetime.now(timezone.utc)

    try:
        weights, thresholds = _load_config(db)
        active_users = _get_active_user_count(db, int(thresholds["active_user_days"]))

        # Fetch full library from Radarr + Sonarr
        library_items = []
        try:
            movies = await stack.radarr.get_all_movies()
            for m in movies:
                library_items.append({
                    "tmdb_id": m.tmdb_id, "media_type": "movie",
                    "servarr_id": m.radarr_id, "title": m.title,
                    "poster_path": m.poster_path,
                    "genres": m.genres, "year": m.year,
                })
        except Exception as e:
            logger.warning("Failed to load movies from Radarr: %s", e)

        try:
            for inst_name, client in stack.registry.get_by_type("sonarr"):
                if client:
                    series = await client.get_all_series()
                    for s in series:
                        library_items.append({
                            "tmdb_id": s.tmdb_id, "media_type": "show",
                            "servarr_id": s.sonarr_id, "title": s.title,
                            "poster_path": s.poster_path,
                            "genres": s.genres, "year": s.year,
                        })
        except Exception as e:
            logger.warning("Failed to load series from Sonarr: %s", e)

        if not library_items:
            logger.warning("No library items found — skipping vitality calculation")
            return {"items": 0, "skipped": True}

        # Aggregate data
        play_stats = _aggregate_play_stats(db)
        rec_freq = _get_rec_frequency(db)
        genre_counts, total_library = _get_genre_distribution(library_items)

        # Score every item
        scored = 0
        zone_counts = {"healthy": 0, "sunset": 0, "dead": 0}

        for item in library_items:
            tmdb_id = item["tmdb_id"]
            mtype = item["media_type"]
            if not tmdb_id:
                continue

            key = (tmdb_id, mtype)
            ps = play_stats.get(key, PlayStats(tmdb_id=tmdb_id, media_type=mtype))

            signals = VitalitySignals(
                tmdb_id=tmdb_id, media_type=mtype,
                servarr_id=item.get("servarr_id"),
                title=item.get("title", ""),
                poster_path=item.get("poster_path"),
            )

            signals.recency = score_recency(ps.last_played, now)
            signals.velocity = score_velocity(ps.monthly_plays, mtype)
            signals.breadth = score_breadth(len(ps.unique_users), active_users)
            signals.rec_frequency = score_rec_frequency(rec_freq.get(key, 0))

            item_genres = [g.lower() if isinstance(g, str) else g for g in item.get("genres", [])]
            signals.niche = score_niche(
                item_genres, genre_counts, total_library, ps.total_plays
            )

            compute_vitality(signals, weights, thresholds)
            zone_counts[signals.zone] = zone_counts.get(signals.zone, 0) + 1

            # Upsert VitalityScore
            existing = db.execute(
                select(VitalityScore).where(
                    VitalityScore.tmdb_id == tmdb_id,
                    VitalityScore.media_type == mtype,
                )
            ).scalar_one_or_none()

            if existing:
                existing.composite_score = signals.composite
                existing.recency_score = signals.recency
                existing.velocity_score = signals.velocity
                existing.breadth_score = signals.breadth
                existing.rec_frequency_score = signals.rec_frequency
                existing.niche_score = signals.niche
                existing.zone = signals.zone
                existing.servarr_id = signals.servarr_id
                existing.title = signals.title
                existing.poster_path = signals.poster_path
                existing.calculated_at = now
            else:
                db.add(VitalityScore(
                    tmdb_id=tmdb_id, media_type=mtype,
                    servarr_id=signals.servarr_id, title=signals.title,
                    poster_path=signals.poster_path,
                    composite_score=signals.composite,
                    recency_score=signals.recency,
                    velocity_score=signals.velocity,
                    breadth_score=signals.breadth,
                    rec_frequency_score=signals.rec_frequency,
                    niche_score=signals.niche,
                    zone=signals.zone, calculated_at=now,
                ))
            scored += 1

        db.commit()

        # Trigger sunset zone transitions
        from app.services.sunset_manager import process_zone_transitions
        transitions = process_zone_transitions(db, thresholds)

        logger.info(
            "Vitality recalc complete: %d items scored, zones: %s, transitions: %s",
            scored, zone_counts, transitions,
        )

        return {
            "items_scored": scored,
            "zones": zone_counts,
            "transitions": transitions,
            "active_users": active_users,
        }

    except Exception as e:
        db.rollback()
        logger.error("Vitality recalculation failed: %s", e, exc_info=True)
        raise
    finally:
        db.close()
