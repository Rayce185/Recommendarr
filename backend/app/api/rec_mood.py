"""Mood parsing and admin/utility endpoints for the recommendation system."""

import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends

from app.services.factory import get_stack
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.cache import get_cache
from app.services.recommender import Recommendation
from app.services.mood_mapper import parse_mood, mood_to_explanation, MOOD_PRESETS
from app.services.ai_mood import parse_mood_ai

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Mood endpoints ───────────────────────────────────────────────

@router.get("/mood/parse")
async def parse_mood_text(text: str = Query(..., min_length=2, max_length=200)):
    """Parse a mood string and return the interpreted vector."""
    vector = await parse_mood_ai(text)
    return {
        "input": text,
        "explanation": mood_to_explanation(vector),
        "confidence": vector.confidence,
        "genre_boost": vector.genre_boost,
        "genre_block": vector.genre_block,
        "keyword_boost": vector.keyword_boost,
        "keyword_block": vector.keyword_block,
        "domain_filter": vector.domain_filter,
        "year_range": vector.year_range,
        "min_rating": vector.min_rating,
        "max_runtime": vector.max_runtime,
        "min_runtime": vector.min_runtime,
        "unparsed_tokens": vector.unparsed_tokens,
    }


@router.get("/mood/presets")
async def get_mood_presets():
    """Get pre-built mood presets for quick-pick UI buttons."""
    presets = []
    for name, query in MOOD_PRESETS.items():
        vector = parse_mood(query)
        presets.append({
            "name": name,
            "query": query,
            "explanation": mood_to_explanation(vector),
            "top_genres": sorted(vector.genre_boost.items(), key=lambda x: x[1], reverse=True)[:3],
        })
    return {"presets": presets}


# ── Admin / utility endpoints ────────────────────────────────────

@router.get("/filters/options")
async def get_filter_options():
    """Available filter options: genres + Plex library sections."""
    stack = get_stack()

    all_genres = set()
    try:
        src = stack.tmdb or stack.seerr
        for g in await src.get_movie_genres():
            all_genres.add(g.get("name", "") if isinstance(g, dict) else str(g))
        for g in await src.get_tv_genres():
            all_genres.add(g.get("name", "") if isinstance(g, dict) else str(g))
    except Exception:
        pass

    libraries = []
    if stack.plex and stack.plex.sections:
        libraries = [
            {"key": s["key"], "title": s["title"], "type": s["type"]}
            for s in stack.plex.sections
        ]

    return {
        "genres": sorted((all_genres | {"Anime"}) - {""}),
        "libraries": libraries,
    }


@router.get("/cache/stats")
async def cache_stats():
    """Cache statistics for monitoring."""
    cache = get_cache()
    return cache.get_stats()


@router.post("/cache/invalidate")
async def invalidate_cache(username: Optional[str] = None):
    """Invalidate cached recommendations."""
    cache = get_cache()
    if username:
        cache.invalidate_user(username)
        return {"status": "ok", "invalidated": username}
    else:
        cache.invalidate_all()
        return {"status": "ok", "invalidated": "all"}


@router.post("/recommend/{username}/explain")
async def lazy_explain(
    username: str,
    user: TokenPayload = Depends(get_current_user),
    mode: str = Query("tonight"),
    domain: str = Query("all"),
):
    """Backfill AI explanations for cached recommendations.

    Call after page load to fill in explanations without blocking initial render.
    Updates the cached response in-place and returns the explanations.
    """
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot explain other users' recommendations")

    cache = get_cache()
    cached = cache.get_recs(username, mode, domain)
    if not cached:
        raise HTTPException(404, "No cached recommendations to explain")

    recs_data = cached.get("recommendations", [])
    has_explanations = any(r.get("explanation") and not r["explanation"].startswith(" ") for r in recs_data[:3])
    if has_explanations:
        return {"status": "already_explained", "count": len(recs_data)}

    from app.services.ai_explanations import generate_explanations, build_profile_summary

    stack = get_stack()
    profile = await stack.profiler.build_profile(username=username, domain=domain, enrich_keywords=True, max_enrich=100)
    cache.set_profile(username, domain, profile)
    profile_summary = build_profile_summary(profile)

    recs = []
    for r in recs_data:
        recs.append(Recommendation(
            tmdb_id=r.get("tmdb_id", 0),
            media_type=r.get("media_type", "movie"),
            title=r.get("title", ""),
            year=r.get("year"),
            genres=r.get("genres", []),
            keywords=r.get("keywords", []),
            overview=r.get("overview"),
            vote_average=r.get("vote_average", 0),
            score=r.get("score", 0),
            score_breakdown=r.get("score_breakdown", {}),
            explanation_signals=r.get("explanation_signals", []),
            mode=mode,
            in_library=r.get("in_library", False),
        ))

    try:
        explanations = await generate_explanations(recs, profile_summary)
        for rec_data, expl in zip(recs_data, explanations):
            rec_data["explanation"] = expl
        cache.set_recs(username, mode, domain, cached)
        return {"status": "explained", "count": len(explanations)}
    except Exception as e:
        logger.warning(f"Lazy explanation failed: {e}")
        raise HTTPException(500, f"Explanation generation failed: {e}")
