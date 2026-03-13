"""Recommendation mode implementations.

Each mode is a standalone async function taking the engine + request.
Modes use rec_scoring and rec_library for heavy lifting.
"""

import logging
import asyncio
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

    # Source 2: Discover by top genres (movies + TV)
    top_genres = profile.top_genres(3)
    for mt in ("movie", "tv"):
        if not engine._genre_cache.get(mt):
            await resolve_genre_ids([], mt, engine.tmdb, engine.seerr, engine._genre_cache)
        reverse_map = {v: k for k, v in engine._genre_cache.get(mt, {}).items()}
        for ga in top_genres:
            genre_id = reverse_map.get(ga.genre)
            if genre_id and engine.tmdb:
                discovered = await engine.tmdb.discover_by_genre(genre_id, mt, 1)
                for item in discovered[:10]:
                    if item.tmdb_id not in exclude:
                        resolver = lambda gids, mtype: resolve_genre_ids(
                            gids, mtype, engine.tmdb, engine.seerr, engine._genre_cache
                        )
                        candidates.append(await discover_to_candidate(item, "discover", resolver))

    # Source 3: Trending page 2
    if engine.tmdb and len(candidates) < 40:
        trending_p2, _ = await engine.tmdb.get_trending("all", "week", 2)
        for item in trending_p2:
            if item.tmdb_id not in exclude:
                resolver = lambda gids, mtype: resolve_genre_ids(
                    gids, mtype, engine.tmdb, engine.seerr, engine._genre_cache
                )
                candidates.append(await discover_to_candidate(item, "trending", resolver))

    # Source 4: Similar to high-completion watched titles (movies + TV)
    history = await engine.tautulli.get_history(user_id=req._uid, limit=500)
    seeds = [e for e in history if e.tmdb_id and e.completion_pct >= 85]
    seeds = random.sample(seeds, min(5, len(seeds))) if seeds else []
    for seed in seeds:
        mt = seed.media_type if seed.media_type in ("movie", "tv") else "movie"
        if engine.tmdb:
            similar = await engine.tmdb.get_similar(seed.tmdb_id, mt, 1)
        else:
            similar = await engine.seerr.get_similar(seed.tmdb_id, mt, 1)
        for item in similar[:8]:
            if item.tmdb_id not in exclude:
                resolver = lambda gids, mtype: resolve_genre_ids(
                    gids, mtype, engine.tmdb, engine.seerr, engine._genre_cache
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

    # Enrich top candidates in parallel batches of 10
    async def _enrich_one(c):
        try:
            detail = await asyncio.wait_for(
                get_detail(c["tmdb_id"], c.get("media_type", "movie"), engine.tmdb, engine.seerr),
                timeout=5.0,
            )
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

    top = candidates[:40]
    for batch_start in range(0, len(top), 10):
        batch = top[batch_start:batch_start + 10]
        await asyncio.gather(*[_enrich_one(c) for c in batch])

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


