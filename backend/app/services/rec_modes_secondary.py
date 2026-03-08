"""Recommendation modes — secondary (rediscover, group, mood).

Extracted from rec_modes.py for §7.7 compliance.
"""

import asyncio
import logging
import random
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from app.services.cache import get_cache
from app.services.rec_types import Recommendation, RecommendationRequest
from app.services.rec_scoring import score_candidate, apply_filters
from app.services.cultural_pulse import get_active_events
from app.services.rec_library import (
    get_library_candidates, get_detail, candidate_to_recommendation,
)
from app.services.mood_mapper import mood_to_explanation
from app.utils.genres import normalize_genres

logger = logging.getLogger(__name__)


def _fetch_pulse() -> list[dict]:
    """Get active cultural pulse events for scoring context."""
    try:
        return get_active_events()
    except Exception:
        return []

async def mode_rediscover(engine, req: RecommendationRequest) -> list[Recommendation]:
    """Titles the user watched and liked, but haven't touched in a while."""
    cache = get_cache()
    history = await engine.tautulli.get_history(user_id=req._uid, limit=5000)
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=180)

    by_item: dict[str, list] = defaultdict(list)
    for e in history:
        by_item[e.item_key].append(e)

    pre_candidates = []
    for item_key, events in by_item.items():
        best_completion = min(max(e.completion_pct for e in events), 100)
        most_recent = max((e.started_at for e in events if e.started_at), default=None)
        if best_completion < 70:
            continue
        if most_recent and most_recent.tzinfo is None:
            most_recent = most_recent.replace(tzinfo=timezone.utc)
        if most_recent and most_recent > stale_threshold:
            continue

        days_since = (now - most_recent).days if most_recent else 365
        pre_candidates.append({
            "item_key": item_key,
            "media_type": events[0].media_type,
            "tmdb_id": events[0].tmdb_id,
            "best_completion": best_completion,
            "days_since": days_since,
            "watch_count": len(events),
            "staleness_score": min(1.0, days_since / 730),
        })

    pre_candidates.sort(
        key=lambda c: c["staleness_score"] * (c["best_completion"] / 100),
        reverse=True,
    )
    pre_candidates = pre_candidates[:req.limit * 3]

    # Resolve TMDB IDs in parallel batches (was sequential — major bottleneck)
    needs_resolve = []
    candidates = []
    for c in pre_candidates:
        tmdb_id = c["tmdb_id"]
        if not tmdb_id:
            cached_tmdb = cache.get_tmdb_id(c["item_key"])
            if cached_tmdb is not None:
                tmdb_id = cached_tmdb
        if tmdb_id:
            if tmdb_id not in req.exclude_tmdb_ids:
                c["tmdb_id"] = tmdb_id
                candidates.append(c)
        else:
            needs_resolve.append(c)

    # Parallel TMDB ID resolution for unresolved items (batches of 10)
    async def _resolve_one(c):
        try:
            tid = await asyncio.wait_for(
                engine.tautulli.resolve_tmdb_id(c["item_key"], c["media_type"]),
                timeout=5.0,
            )
            if tid:
                cache.set_tmdb_id(c["item_key"], tid)
                c["tmdb_id"] = tid
                return c
        except Exception:
            pass
        return None

    for batch_start in range(0, min(len(needs_resolve), 30), 10):
        batch = needs_resolve[batch_start:batch_start + 10]
        resolved = await asyncio.gather(*[_resolve_one(c) for c in batch])
        for c in resolved:
            if c and c["tmdb_id"] not in req.exclude_tmdb_ids:
                candidates.append(c)

    candidates = apply_filters(candidates, req)
    candidates = candidates[:req.limit * 2]

    scored = []
    for c in candidates[:req.limit]:
        try:
            mt = "movie" if c["media_type"] == "movie" else "tv"
            detail = await get_detail(c["tmdb_id"], mt, engine.tmdb, engine.seerr)
            rec = Recommendation(
                tmdb_id=c["tmdb_id"], media_type=mt,
                title=detail["title"], year=detail.get("year"),
                poster_path=detail.get("poster_path"),
                backdrop_path=detail.get("backdrop_path"),
                genres=normalize_genres(detail.get("genres", []), original_language=detail.get("original_language")),
                keywords=detail.get("keywords", [])[:10],
                overview=detail.get("overview", ""),
                vote_average=detail.get("vote_average", 0),
                runtime=detail.get("runtime"),
                original_language=detail.get("original_language"),
                score=c["staleness_score"] * (c["best_completion"] / 100),
                score_breakdown={"staleness": c["staleness_score"], "completion": c["best_completion"] / 100},
                mode="rediscover", in_library=True,
                directors=detail.get("directors", []),
                cast=[x["name"] if isinstance(x, dict) else x for x in detail.get("cast", [])[:5]],
                trailer_key=detail.get("trailers", [{}])[0].get("key") if detail.get("trailers") else None,
            )
            signals = []
            if c["days_since"] > 365:
                signals.append(f"Last watched {c['days_since'] // 365} years ago")
            else:
                signals.append(f"Last watched {c['days_since'] // 30} months ago")
            if c["watch_count"] > 1:
                signals.append(f"Watched {c['watch_count']} times")
            signals.append(f"{c['best_completion']:.0f}% completion")
            rec.explanation = " · ".join(signals)
            rec.explanation_signals = signals
            scored.append(rec)
        except Exception as e:
            logger.debug(f"Rediscover enrich failed: {e}")

    return scored


async def mode_group_night(engine, req: RecommendationRequest) -> list[Recommendation]:
    """Find titles matching taste intersection of multiple users."""
    if len(req.group_users) < 2:
        return []

    profiles = {}
    for user in req.group_users:
        profiles[user] = await engine._get_profile(user, req.domain)

    candidates = await get_library_candidates(
        engine.radarr, engine.sonarr_tv, engine.sonarr_anime, req.domain
    )
    candidates = apply_filters(candidates, req)

    scored = []
    pulse = _fetch_pulse()
    for candidate in candidates:
        if candidate.get("tmdb_id", 0) in req.exclude_tmdb_ids:
            continue
        scores_per_user = {}
        for user, profile in profiles.items():
            s, bd, sig = score_candidate(candidate, profile, req.mood_vector, getattr(req, '_overrides', None), pulse_events=pulse)
            scores_per_user[user] = s

        group_score = min(scores_per_user.values()) if scores_per_user else 0
        avg_score = sum(scores_per_user.values()) / len(scores_per_user) if scores_per_user else 0
        final_score = 0.7 * group_score + 0.3 * avg_score

        rec = candidate_to_recommendation(candidate, final_score, {"per_user": scores_per_user}, [], "group")
        rec.explanation = f"Group fit: {' / '.join(f'{u}:{s:.0%}' for u, s in scores_per_user.items())}"
        scored.append(rec)

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:req.limit]


async def mode_mood_match(engine, req: RecommendationRequest) -> list[Recommendation]:
    """Apply mood vector to library, combining with taste profile."""
    profile = await engine._get_profile(req.username, req.domain)
    candidates = await get_library_candidates(
        engine.radarr, engine.sonarr_tv, engine.sonarr_anime, req.domain
    )
    candidates = apply_filters(candidates, req)

    pulse = _fetch_pulse()
    scored = []
    for candidate in candidates:
        if candidate.get("tmdb_id", 0) in req.exclude_tmdb_ids:
            continue
        score, breakdown, signals = score_candidate(
            candidate, profile, req.mood_vector, getattr(req, '_overrides', None),
            pulse_events=pulse,
        )
        scored.append(candidate_to_recommendation(candidate, score, breakdown, signals, "mood"))

    scored.sort(key=lambda r: r.score, reverse=True)
    result = scored[:req.limit]

    mood_explanation = mood_to_explanation(req.mood_vector)
    for rec in result:
        rec.explanation = f"Mood: {mood_explanation} · {rec.explanation}"
    return result

