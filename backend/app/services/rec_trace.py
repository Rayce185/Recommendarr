"""Recommendation Trace — "Because You Watched X" attribution.

Post-hoc enrichment: given a set of recommendations and a user's watch
history, find the specific watched titles that best explain each rec.
Uses genre, keyword, and personnel overlap as matching signals.
"""

import json
import logging
from typing import Optional
from collections import defaultdict

from app.services.rec_types import Recommendation
from app.services.cache import get_cache

logger = logging.getLogger(__name__)


def _title_overlap_score(rec: Recommendation, watched_item: dict) -> float:
    """Score how well a watched title explains a recommendation.

    Returns a 0.0–1.0 overlap score based on shared genres, keywords,
    and personnel.
    """
    score = 0.0

    # Genre overlap (strongest signal)
    rec_genres = set(g.lower() if isinstance(g, str) else g for g in rec.genres)
    w_genres = set(
        g.lower() if isinstance(g, str) else g.get("name", "").lower()
        for g in watched_item.get("genres", [])
    )
    if rec_genres and w_genres:
        genre_overlap = len(rec_genres & w_genres) / max(len(rec_genres), 1)
        score += genre_overlap * 0.5

    # Keyword overlap
    rec_kw = set(k.lower() for k in rec.keywords[:20])
    w_kw = set(k.lower() for k in watched_item.get("keywords", [])[:20])
    if rec_kw and w_kw:
        kw_overlap = len(rec_kw & w_kw) / max(len(rec_kw), 1)
        score += kw_overlap * 0.3

    # Director overlap
    rec_dirs = set(d.lower() for d in rec.directors)
    w_dirs = set(d.lower() for d in watched_item.get("directors", []))
    if rec_dirs & w_dirs:
        score += 0.2

    return min(1.0, score)


def _shared_features(rec: Recommendation, watched_item: dict) -> list[str]:
    """Get human-readable list of shared features between rec and watched item."""
    features = []

    rec_genres = set(g.lower() if isinstance(g, str) else g for g in rec.genres)
    w_genres = set(
        g.lower() if isinstance(g, str) else g.get("name", "").lower()
        for g in watched_item.get("genres", [])
    )
    shared_g = rec_genres & w_genres
    if shared_g:
        features.append(", ".join(sorted(shared_g)[:3]))

    rec_dirs = set(d for d in rec.directors)
    w_dirs = set(d for d in watched_item.get("directors", []))
    shared_d = rec_dirs & w_dirs
    if shared_d:
        features.extend(f"directed by {d}" for d in sorted(shared_d)[:2])

    return features


def enrich_with_traces(
    recommendations: list[Recommendation],
    watched_titles: list[dict],
    max_traces: int = 3,
    min_overlap: float = 0.2,
) -> list[Recommendation]:
    """Add 'because you watched' traces to each recommendation.

    Args:
        recommendations: Scored recommendation list
        watched_titles: User's watch history with TMDB metadata
            Each dict should have: title, tmdb_id, genres, keywords, directors
        max_traces: Max number of trace titles per recommendation
        min_overlap: Minimum overlap score to include as trace

    Returns:
        Same recommendations list, mutated with trace data in explanation_signals.
    """
    if not watched_titles or not recommendations:
        return recommendations

    for rec in recommendations:
        traces = []
        for w in watched_titles:
            # Skip self-references
            if w.get("tmdb_id") == rec.tmdb_id:
                continue
            overlap = _title_overlap_score(rec, w)
            if overlap >= min_overlap:
                features = _shared_features(rec, w)
                traces.append({
                    "title": w.get("title", "Unknown"),
                    "tmdb_id": w.get("tmdb_id"),
                    "overlap": round(overlap, 3),
                    "features": features,
                })

        # Sort by overlap, take top N
        traces.sort(key=lambda t: t["overlap"], reverse=True)
        top_traces = traces[:max_traces]

        if top_traces:
            # Add to explanation_signals
            trace_strs = []
            for t in top_traces:
                feat_str = f" ({', '.join(t['features'])})" if t["features"] else ""
                trace_strs.append(f"Because you watched {t['title']}{feat_str}")

            if not rec.explanation_signals:
                rec.explanation_signals = []
            rec.explanation_signals = trace_strs + rec.explanation_signals

    return recommendations


def _parse_json_field(val):
    """Parse a JSON field that might be a string, list, dict, or None."""
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, (list, dict)) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


async def get_watched_titles_for_traces(
    tautulli,
    tmdb,
    username: str,
    user_id: str,
    limit: int = 100,
) -> list[dict]:
    """Get library items with TMDB metadata for trace matching.

    Uses TmdbCache directly — these are items from the user's Plex library
    that have been enriched with genre/keyword/personnel data during
    library scans and recommendation generation.
    """
    from sqlalchemy import select
    from app.database import get_db
    from app.models.tables import TmdbCache

    try:
        db = get_db()
        cache_rows = db.execute(
            select(TmdbCache).limit(limit)
        ).scalars().all()
        db.close()

        if not cache_rows:
            return []

        watched = []
        for cr in cache_rows:
            genres = _parse_json_field(cr.genres)
            keywords = _parse_json_field(cr.keywords)
            cast_crew = _parse_json_field(cr.cast_crew)
            directors = cast_crew.get("directors", []) if isinstance(cast_crew, dict) else []

            watched.append({
                "tmdb_id": cr.tmdb_id,
                "title": cr.title,
                "genres": genres,
                "keywords": keywords,
                "directors": directors,
            })

        logger.info(f"Traces: loaded {len(watched)} library items for {username}")
        return watched

    except Exception as e:
        logger.warning(f"Failed to get library items for traces: {e}")
        return []
