"""Action API routes — media requests, watchlists, cache management, explanations.

Handles Seerr proxying, Plex watchlist ops, and AI explanation backfill.
"""

import logging
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional

from app.services.factory import get_stack
from app.services.feedback import get_feedback_store
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/request/{tmdb_id}")
async def request_media(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    seasons: Optional[str] = None,
):
    """Submit a media request through Seerr -> Radarr/Sonarr."""
    stack = get_stack()
    try:
        if media_type == "movie":
            result = await stack.seerr.request_movie(tmdb_id)
        else:
            season_list = None
            if seasons:
                season_list = [int(s.strip()) for s in seasons.split(",")]
            result = await stack.seerr.request_tv(tmdb_id, season_list)
    except Exception as e:
        raise HTTPException(400, f"Request failed: {e}")
    return {
        "request_id": result.request_id, "tmdb_id": result.tmdb_id,
        "media_type": result.media_type, "status": result.status,
        "requested_by": result.requested_by,
    }


@router.post("/watchlist/add/{tmdb_id}")
async def add_to_watchlist(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Add a title to the authenticated user's Plex watchlist."""
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")
    plex_guid = await stack.plex.resolve_plex_guid(tmdb_id, media_type)
    if not plex_guid:
        raise HTTPException(404, f"Could not resolve TMDB {tmdb_id} to Plex metadata")
    success = await stack.plex.add_to_watchlist(plex_guid, token_override=user.plex_token)
    if not success:
        raise HTTPException(500, "Failed to add to Plex watchlist")
    return {"success": True, "tmdb_id": tmdb_id, "plex_guid": plex_guid, "user": user.username}


@router.post("/watchlist/remove/{tmdb_id}")
async def remove_from_watchlist(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Remove a title from the authenticated user's Plex watchlist."""
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")
    plex_guid = await stack.plex.resolve_plex_guid(tmdb_id, media_type)
    if not plex_guid:
        raise HTTPException(404, f"Could not resolve TMDB {tmdb_id} to Plex metadata")
    success = await stack.plex.remove_from_watchlist(plex_guid, token_override=user.plex_token)
    if not success:
        raise HTTPException(500, "Failed to remove from Plex watchlist")
    return {"success": True, "tmdb_id": tmdb_id, "user": user.username}


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
        libraries = [{"key": s["key"], "title": s["title"], "type": s["type"]} for s in stack.plex.sections]
    return {"genres": sorted((all_genres | {"Anime"}) - {""}), "libraries": libraries}


@router.get("/cache/stats")
async def cache_stats():
    """Cache statistics for monitoring."""
    return get_cache().get_stats()


@router.post("/cache/invalidate")
async def invalidate_cache(username: Optional[str] = None):
    """Invalidate cached recommendations (all or per-user)."""
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
    """Backfill AI explanations for cached recommendations."""
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

    from app.services.recommender import Recommendation
    from app.services.ai_explanations import generate_explanations, build_profile_summary

    stack = get_stack()
    profile = await stack.profiler.build_profile(username=username, domain=domain, enrich_keywords=True, max_enrich=100)
    cache.set_profile(username, domain, profile)
    profile_summary = build_profile_summary(profile)

    recs = []
    for r in recs_data:
        recs.append(Recommendation(
            tmdb_id=r.get("tmdb_id", 0), media_type=r.get("media_type", "movie"),
            title=r.get("title", ""), year=r.get("year"),
            genres=r.get("genres", []), keywords=r.get("keywords", []),
            overview=r.get("overview"), vote_average=r.get("vote_average", 0),
            score=r.get("score", 0), score_breakdown=r.get("score_breakdown", {}),
            explanation_signals=r.get("explanation_signals", []),
            mode=mode, in_library=r.get("in_library", False),
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
