"""Recommendation API — Core recommendation, mood, and admin endpoints.

All endpoints use the service stack (Tautulli + Seerr + Radarr/Sonarr)
through the RecommendationEngine orchestrator.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends

from app.services.factory import get_stack
from app.services.profile_overrides import get_override_store
from app.services.feedback import get_feedback_store
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.config import settings
from app.services.cache import get_cache
from app.services.recommender import RecommendationRequest, Recommendation
from app.services.mood_mapper import parse_mood, mood_to_explanation, MOOD_PRESETS
from app.services.ai_mood import parse_mood_ai
from app.api.rec_helpers import rec_to_dict

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Core recommendation endpoints ────────────────────────────────

@router.get("/recommend/{username}")
async def get_recommendations(
    username: str,
    mode: str = Query("tonight", pattern="^(tonight|grab|rediscover|mood|group)$"),
    domain: str = Query("all", pattern="^(all|movies|tv|anime)$"),
    limit: int = Query(20, ge=1, le=50),
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    exclude: Optional[str] = None,
    exclude_genres: Optional[str] = Query(None, description="Comma-separated genre names to exclude"),
    include_genres: Optional[str] = Query(None, description="Comma-separated genre names to include"),
    exclude_libraries: Optional[str] = Query(None, description="Comma-separated Plex library names to exclude"),
    watched_filter: str = Query("all", pattern="^(all|unseen|seen)$", description="Filter by watched status"),
    refresh: bool = Query(False, description="Force cache refresh"),
):
    """Get personalized recommendations.

    Modes: tonight (in-library), grab (discover), rediscover (rewatchable),
    mood (NL input), group (multi-user intersection).
    """
    stack = get_stack()

    exclude_ids = set()
    if exclude:
        try:
            exclude_ids = {int(x.strip()) for x in exclude.split(",") if x.strip()}
        except ValueError:
            raise HTTPException(400, "exclude must be comma-separated TMDB IDs")

    # Parse mood if provided
    mood_vector = None
    if mood:
        mood_vector = await parse_mood_ai(mood)

    # Parse filter params
    excl_genres = {g.strip() for g in exclude_genres.split(",") if g.strip()} if exclude_genres else set()
    incl_genres = {g.strip() for g in include_genres.split(",") if g.strip()} if include_genres else set()
    excl_libs = {l.strip() for l in exclude_libraries.split(",") if l.strip()} if exclude_libraries else set()

    req = RecommendationRequest(
        username=username,
        mode=mode,
        domain=domain,
        limit=limit,
        genre_filter=genre,
        mood_vector=mood_vector,
        mood_text=mood if mode == "mood" else None,
        exclude_tmdb_ids=exclude_ids,
        exclude_genres=excl_genres,
        include_genres=incl_genres,
        exclude_libraries=excl_libs,
    )

    # Group mode: extract usernames
    if mode == "group" and mood:
        req.group_users = [u.strip() for u in mood.split(",") if u.strip()]
        req.mood_vector = None
        req.mood_text = None

    # Check cache first (unless force refresh or dynamic params)
    cache = get_cache()
    has_filters = exclude or exclude_genres or include_genres or exclude_libraries
    cache_eligible = mode not in ("mood", "group") and not has_filters and not mood
    cached_response = None
    if cache_eligible and not refresh:
        cached_response = cache.get_recs(username, mode, domain)

    if cached_response is not None:
        cached_response["meta"]["cached"] = True
        cache_age = cache.get_recs_age(username, mode, domain)
        cached_response["meta"]["cache_age_seconds"] = round(cache_age, 1) if cache_age is not None else None
        cached_response["meta"]["profile_modified_at"] = get_override_store().get_updated_at(username)
        fb_store = get_feedback_store()
        for rec in cached_response.get("recommendations", []):
            rec["user_feedback"] = fb_store.get_action(username, rec.get("tmdb_id"))
        return cached_response

    try:
        recs = await stack.engine.recommend(req)
    except Exception as e:
        raise HTTPException(500, f"Recommendation engine error: {str(e)}")

    response = {
        "recommendations": [
            rec_to_dict(r, plex=stack.plex)
            for r in recs
            if (watched_filter == "all" or (watched_filter == "unseen" and not r.is_watched) or (watched_filter == "seen" and r.is_watched))
        ],
        "meta": {
            "username": username,
            "mode": mode,
            "domain": domain,
            "count": len(recs),
            "cached": False,
            "genre_filter": genre,
            "profile_modified_at": get_override_store().get_updated_at(username),
        },
    }

    if mood_vector:
        response["meta"]["mood"] = {
            "input": mood,
            "parsed": mood_to_explanation(mood_vector),
            "confidence": mood_vector.confidence,
            "genre_boost": mood_vector.genre_boost,
            "genre_block": mood_vector.genre_block,
            "keyword_boost": mood_vector.keyword_boost[:10],
        }

    fb_store = get_feedback_store()
    for rec in response["recommendations"]:
        rec["user_feedback"] = fb_store.get_action(username, rec["tmdb_id"])

    if cache_eligible:
        cache.set_recs(username, mode, domain, response)

    return response


@router.get("/recommend/{username}/group")
async def get_group_recommendations(
    username: str,
    users: str = Query(..., description="Comma-separated usernames including requesting user"),
    domain: str = Query("all", pattern="^(all|movies|tv|anime)$"),
    limit: int = Query(20, ge=1, le=50),
    genre: Optional[str] = None,
    watched_filter: str = Query("all", pattern="^(all|unseen|seen)$"),
):
    """Group Night — find titles matching taste intersection of multiple users."""
    stack = get_stack()

    user_list = [u.strip() for u in users.split(",") if u.strip()]
    if len(user_list) < 2:
        raise HTTPException(400, "Group mode requires at least 2 usernames")

    req = RecommendationRequest(
        username=username,
        mode="group",
        domain=domain,
        limit=limit,
        genre_filter=genre,
        group_users=user_list,
    )

    recs = await stack.engine.recommend(req)

    return {
        "recommendations": [
            rec_to_dict(r, plex=stack.plex)
            for r in recs
            if (watched_filter == "all" or (watched_filter == "unseen" and not r.is_watched) or (watched_filter == "seen" and r.is_watched))
        ],
        "meta": {
            "mode": "group",
            "group_users": user_list,
            "count": len(recs),
        },
    }


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
