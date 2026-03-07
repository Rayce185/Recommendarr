"""Recommendation mode implementations.

Each mode is a standalone async function taking the engine + request.
Modes use rec_scoring and rec_library for heavy lifting.
"""

import logging
import random
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.services.cache import get_cache
from app.services.rec_types import Recommendation, RecommendationRequest
from app.services.rec_scoring import score_candidate, apply_filters
from app.services.cultural_pulse import get_active_events
from app.services.rec_library import (
    get_library_candidates, get_library_tmdb_ids,
    get_detail, discover_to_candidate, candidate_to_recommendation,
    resolve_genre_ids,
)
from app.services.mood_mapper import mood_to_explanation
from app.utils.genres import normalize_genres

logger = logging.getLogger(__name__)


def _fetch_pulse() -> list[dict]:
    """Fetch active cultural pulse events for scoring injection."""
    try:
        return get_active_events(limit=10)
    except Exception:
        return []


async def mode_tonight(engine, req: RecommendationRequest) -> list[Recommendation]:
    """In-library recommendations scored against user taste."""
    profile = await engine._get_profile(req.username, req.domain)
    candidates = await get_library_candidates(
        engine.radarr, engine.sonarr_tv, engine.sonarr_anime, req.domain
    )
    candidates = apply_filters(candidates, req)

    from app.services.factory import get_stack
    stack = get_stack()
    plex = stack.plex if stack else None

    user_section_counts: dict[str, int] = {}
    if plex and plex._watched_map:
        for key, vc in plex._watched_map.items():
            sec = plex._section_map.get(key, "")
            if sec:
                user_section_counts[sec] = user_section_counts.get(sec, 0) + vc

    pulse = _fetch_pulse()
    scored = []
    for candidate in candidates:
        tmdb_id = candidate.get("tmdb_id", 0)
        media_type = candidate.get("media_type", "movie")
        if tmdb_id in req.exclude_tmdb_ids:
            continue

        is_watched = plex.is_watched(tmdb_id, media_type) if plex else False

        score, breakdown, signals = score_candidate(
            candidate, profile, req.mood_vector, getattr(req, '_overrides', None),
            pulse_events=pulse,
        )

        if plex and user_section_counts:
            section = plex.get_section_name(tmdb_id, media_type)
            if section:
                sec_watches = user_section_counts.get(section, 0)
                total_watches = sum(user_section_counts.values())
                sec_ratio = sec_watches / total_watches if total_watches > 0 else 0
                if sec_ratio < 0.02:
                    score *= 0.3
                    signals.append(f"Low affinity: {section}")
                elif sec_ratio < 0.10:
                    score *= 0.6
                    signals.append(f"Moderate affinity: {section}")

        rec = candidate_to_recommendation(candidate, score, breakdown, signals, "tonight")
        rec.is_watched = is_watched
        scored.append(rec)

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:req.limit]


async def mode_worth_grabbing(engine, req: RecommendationRequest) -> list[Recommendation]:
    """Beyond-library recommendations from TMDB discover/trending."""
    profile = await engine._get_profile(req.username, req.domain)
    library_ids = await get_library_tmdb_ids(
        engine.radarr, engine.sonarr_tv, engine.sonarr_anime, req.domain
    )
    exclude = req.exclude_tmdb_ids | library_ids

    candidates: list[dict] = []

    # Source 1: Trending
    if engine.tmdb:
        trending_raw, _ = await engine.tmdb.get_trending("all", "week", 1)
    else:
        trending_raw = await engine.seerr.get_trending(1)
    for item in trending_raw:
        if item.tmdb_id not in exclude:
            resolver = lambda gids, mt: resolve_genre_ids(
                gids, mt, engine.tmdb, engine.seerr, engine._genre_cache
            )
            candidates.append(await discover_to_candidate(item, "trending", resolver))

    # Source 2: Discover by top genres
    top_genres = profile.top_genres(3)
    if not engine._genre_cache.get("movie"):
        await resolve_genre_ids([], "movie", engine.tmdb, engine.seerr, engine._genre_cache)
    reverse_map = {v: k for k, v in engine._genre_cache.get("movie", {}).items()}
    for ga in top_genres:
        genre_id = reverse_map.get(ga.genre)
        if genre_id:
            if engine.tmdb:
                discovered = await engine.tmdb.discover_by_genre(genre_id, "movie", 1)
            else:
                discovered = await engine.seerr.discover_movies(page=1, genre=genre_id)
            for item in discovered[:10]:
                if item.tmdb_id not in exclude:
                    resolver = lambda gids, mt: resolve_genre_ids(
                        gids, mt, engine.tmdb, engine.seerr, engine._genre_cache
                    )
                    candidates.append(await discover_to_candidate(item, "discover", resolver))

    # Source 3: Similar to high-completion watched titles
    history = await engine.tautulli.get_history(user_id=req._uid, limit=3000)
    seeds = [e for e in history if e.tmdb_id and e.completion_pct >= 85]
    seeds = random.sample(seeds, min(3, len(seeds))) if seeds else []
    for seed in seeds:
        if engine.tmdb:
            similar = await engine.tmdb.get_similar(seed.tmdb_id, "movie", 1)
        else:
            similar = await engine.seerr.get_similar(seed.tmdb_id, "movie", 1)
        for item in similar[:8]:
            if item.tmdb_id not in exclude:
                resolver = lambda gids, mt: resolve_genre_ids(
                    gids, mt, engine.tmdb, engine.seerr, engine._genre_cache
                )
                candidates.append(await discover_to_candidate(item, "similar", resolver))

    # Deduplicate
    seen = set()
    unique = []
    for c in candidates:
        tid = c.get("tmdb_id", 0)
        if tid not in seen:
            seen.add(tid)
            unique.append(c)
    candidates = apply_filters(unique, req)

    # Enrich top candidates
    for c in candidates[:40]:
        try:
            detail = await get_detail(c["tmdb_id"], c.get("media_type", "movie"), engine.tmdb, engine.seerr)
            c["keywords"] = detail["keywords"]
            c["directors"] = detail["directors"]
            c["cast"] = [x["name"] if isinstance(x, dict) else x for x in detail.get("cast", [])[:5]]
            c["overview"] = detail["overview"]
            c["runtime"] = detail.get("runtime")
            c["original_language"] = detail.get("original_language")
            if detail.get("trailers"):
                c["trailer_key"] = detail["trailers"][0].get("key")
                c["trailer_site"] = detail["trailers"][0].get("site")
        except Exception as e:
            logger.debug(f"Enrich failed for {c.get('tmdb_id')}: {e}")

    pulse = _fetch_pulse()
    scored = []
    for candidate in candidates:
        score, breakdown, signals = score_candidate(
            candidate, profile, req.mood_vector, getattr(req, '_overrides', None),
            pulse_events=pulse,
        )
        scored.append(candidate_to_recommendation(candidate, score, breakdown, signals, "grab"))

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:req.limit]


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

    candidates = []
    for c in pre_candidates:
        tmdb_id = c["tmdb_id"]
        if not tmdb_id:
            cached_tmdb = cache.get_tmdb_id(c["item_key"])
            if cached_tmdb is not None:
                tmdb_id = cached_tmdb
            else:
                try:
                    tmdb_id = await engine.tautulli.resolve_tmdb_id(c["item_key"], c["media_type"])
                    cache.set_tmdb_id(c["item_key"], tmdb_id)
                except Exception:
                    pass
        if not tmdb_id or tmdb_id in req.exclude_tmdb_ids:
            continue
        c["tmdb_id"] = tmdb_id
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
