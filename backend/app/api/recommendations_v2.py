"""Recommendation API v2 — API-first, no DB dependency for core flow.

All endpoints use the service stack (Tautulli + Seerr + Radarr/Sonarr)
through the RecommendationEngineV2 orchestrator.
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional

from app.services.factory import get_stack
from app.services.profile_overrides import get_override_store
from app.services.feedback import get_feedback_store
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.config import settings
from app.services.cache import get_cache
from app.services.recommender_v2 import RecommendationRequest, Recommendation
from app.services.mood_mapper import parse_mood, mood_to_explanation, MOOD_PRESETS
from app.clients.tmdb import TMDBClient, COUNTRY_OPTIONS

router = APIRouter()


def _img_url(path: str | None, size: str = "w342") -> str | None:
    """Build TMDB image URL, handling both relative paths and absolute URLs."""
    if not path:
        return None
    if path.startswith("http"):
        return path  # Already a full URL (Radarr/Sonarr/TVDB)
    return f"https://image.tmdb.org/t/p/{size}{path}"


def _rec_to_dict(r: Recommendation, plex=None) -> dict:
    """Serialize a Recommendation to API response format."""
    # Build action URLs
    plex_url = None
    seerr_url = None
    if r.in_library and plex:
        plex_url = plex.get_plex_url(r.tmdb_id, r.media_type)
    if not r.in_library and settings.seerr_url:
        seerr_url = f"{settings.seerr_url}/{r.media_type}/{r.tmdb_id}"

    return {
        "tmdb_id": r.tmdb_id,
        "media_type": r.media_type,
        "title": r.title,
        "year": r.year,
        "poster_url": _img_url(r.poster_path, "w342"),
        "backdrop_url": _img_url(r.backdrop_path, "w1280"),
        "trailer_url": f"https://www.youtube-nocookie.com/embed/{r.trailer_key}" if r.trailer_key else None,
        "genres": r.genres,
        "keywords": r.keywords,
        "overview": r.overview,
        "vote_average": r.vote_average,
        "runtime": r.runtime,
        "original_language": r.original_language,
        "score": round(r.score, 4),
        "score_breakdown": r.score_breakdown,
        "explanation": r.explanation,
        "explanation_signals": r.explanation_signals,
        "mode": r.mode,
        "in_library": r.in_library,
        "quality": r.quality,
        "source": r.source,
        "directors": r.directors,
        "cast": r.cast[:5],
        "plex_url": plex_url,
        "seerr_url": seerr_url,
        "is_watched": r.is_watched,
    }


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
    hide_watched: bool = Query(False, description="Hide already-watched items"),
    refresh: bool = Query(False, description="Force cache refresh"),
):
    """Get personalized recommendations.

    Modes:
    - tonight: In-library, unwatched, scored by taste
    - grab: Not in library, discover via TMDB trending/similar
    - rediscover: Previously watched + liked, stale for 6+ months
    - mood: Natural language input parsed into genre/keyword weights
    - group: Multi-user intersection (pass comma-separated usernames)

    Args:
        username: Plex/Tautulli username
        mode: Recommendation mode
        domain: Filter by media domain (movies/tv/anime/all)
        limit: Max results (1-50)
        genre: Filter to specific genre name
        mood: Natural language mood string (used with mode=mood or as overlay)
        exclude: Comma-separated TMDB IDs to exclude
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
        mood_vector = parse_mood(mood)

    # Parse filter params
    excl_genres = {g.strip() for g in exclude_genres.split(",") if g.strip()} if exclude_genres else set()
    incl_genres = {g.strip() for g in include_genres.split(",") if g.strip()} if include_genres else set()
    excl_libs = {l.strip() for l in exclude_libraries.split(",") if l.strip()} if exclude_libraries else set()

    # Build request
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
        # Overload: for group mode, pass usernames in 'mood' param as comma-separated
        req.group_users = [u.strip() for u in mood.split(",") if u.strip()]
        req.mood_vector = None
        req.mood_text = None

    # Check cache first (unless force refresh or mood/group/exclude which are dynamic)
    cache = get_cache()
    has_filters = exclude or exclude_genres or include_genres or exclude_libraries
    cache_eligible = mode not in ("mood", "group") and not has_filters and not mood
    cached_response = None
    if cache_eligible and not refresh:
        cached_response = cache.get_recs(username, mode, domain)

    if cached_response is not None:
        # Add cache flag + age to meta
        cached_response["meta"]["cached"] = True
        cache_age = cache.get_recs_age(username, mode, domain)
        cached_response["meta"]["cache_age_seconds"] = round(cache_age, 1) if cache_age is not None else None
        cached_response["meta"]["profile_modified_at"] = get_override_store().get_updated_at(username)
        # Refresh feedback state (may have changed since cache)
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
                _rec_to_dict(r, plex=stack.plex)
                for r in recs
                if not (hide_watched and r.is_watched)
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

    # Include mood parse info if mood was provided
    if mood_vector:
        response["meta"]["mood"] = {
            "input": mood,
            "parsed": mood_to_explanation(mood_vector),
            "confidence": mood_vector.confidence,
            "genre_boost": mood_vector.genre_boost,
            "genre_block": mood_vector.genre_block,
            "keyword_boost": mood_vector.keyword_boost[:10],
        }

    # Inject user feedback state into each rec
    fb_store = get_feedback_store()
    for rec in response["recommendations"]:
        rec["user_feedback"] = fb_store.get_action(username, rec["tmdb_id"])

    # Cache result for future requests
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
    hide_watched: bool = Query(False, description="Hide already-watched items"),
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
                _rec_to_dict(r, plex=stack.plex)
                for r in recs
                if not (hide_watched and r.is_watched)
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
    """Parse a mood string and return the interpreted vector.

    Useful for UI preview — show users how their mood text is interpreted
    before running the full recommendation.
    """
    vector = parse_mood(text)
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


# ── Discovery endpoints (Seerr proxy) ───────────────────────────

@router.get("/discover/trending")
async def get_trending(
    source: str = Query("global", pattern="^(global|country|provider|new_releases)$"),
    media_type: str = Query("all", pattern="^(all|movie|tv|anime)$"),
    region: str = Query("CH", max_length=2),
    provider_id: Optional[int] = Query(None, description="Streaming provider ID from /discover/providers"),
    days: int = Query(90, ge=7, le=365, description="New releases window in days"),
    page: int = Query(1, ge=1),
):
    """Expanded trending with multiple sources.

    Sources:
    - global: TMDB global trending (movies + TV)
    - country: Popular content by country/region
    - provider: Popular on a specific streaming provider
    - new_releases: Recently released, sorted by popularity
    """
    stack = get_stack()

    def _fmt(t) -> dict:
        """Format a TMDB result for API response."""
        poster = None
        if t.poster_path:
            poster = f"https://image.tmdb.org/t/p/w342{t.poster_path}" if not t.poster_path.startswith("http") else t.poster_path
        return {
            "tmdb_id": t.tmdb_id,
            "media_type": t.media_type,
            "title": t.title,
            "year": t.year,
            "poster_url": poster,
            "vote_average": t.vote_average,
            "genres": stack.seerr.resolve_genre_ids(t.genre_ids, t.media_type) if hasattr(t, "genre_ids") else [],
            "popularity": getattr(t, "popularity", 0),
            "original_language": getattr(t, "original_language", None),
            "release_date": getattr(t, "release_date", None),
        }

    # Use direct TMDB client if available, fall back to Seerr
    if stack.tmdb:
        if source == "global":
            if media_type == "anime":
                # Global trending anime: discover/tv with animation genre + Japanese
                d = await stack.tmdb._get("/discover/tv", {
                    "sort_by": "popularity.desc",
                    "with_genres": "16",
                    "with_original_language": "ja",
                    "page": page,
                    "vote_count.gte": 5,
                })
                results = [stack.tmdb._parse_result(r, "tv") for r in d.get("results", [])]
                total_pages = d.get("total_pages", 1)
            else:
                mt = media_type if media_type != "all" else "all"
                results, total_pages = await stack.tmdb.get_trending(mt, "week", page)
        elif source == "country":
            mt = media_type if media_type != "all" else "movie"
            results, total_pages = await stack.tmdb.discover_by_country(region, mt, page)
        elif source == "provider":
            if not provider_id:
                raise HTTPException(400, "provider_id required for source=provider")
            mt = media_type if media_type != "all" else "movie"
            results, total_pages = await stack.tmdb.discover_by_provider(provider_id, region, mt, page)
        elif source == "new_releases":
            mt = media_type if media_type != "all" else "movie"
            results, total_pages = await stack.tmdb.discover_new_releases(days, mt, page)
        else:
            results, total_pages = [], 0

        # Anime filter: re-query as TV with animation genre + Japanese language
        if media_type == "anime" and source != "global":
            from datetime import datetime, timedelta
            anime_params = {
                "sort_by": "popularity.desc",
                "with_genres": "16",
                "with_original_language": "ja",
                "page": page,
                "vote_count.gte": 5,
            }
            if source == "country":
                anime_params["watch_region"] = region
            elif source == "provider" and provider_id:
                anime_params["watch_region"] = region
                anime_params["with_watch_providers"] = str(provider_id)
            elif source == "new_releases":
                now = __import__("datetime").datetime.utcnow()
                anime_params["first_air_date.gte"] = (now - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
                anime_params["first_air_date.lte"] = now.strftime("%Y-%m-%d")
            d = await stack.tmdb._get("/discover/tv", anime_params)
            results = [stack.tmdb._parse_result(r, "tv") for r in d.get("results", [])]
            total_pages = d.get("total_pages", 1)

        return {
            "results": [_fmt(r) for r in results],
            "source": source,
            "region": region,
            "media_type": media_type,
            "page": page,
            "total_pages": min(total_pages, 20),  # Cap at 20 pages
        }
    else:
        # Fallback: Seerr trending (global only)
        trending = await stack.seerr.get_trending(page=page)
        return {
            "results": [_fmt(t) for t in trending],
            "source": "global",
            "page": page,
            "total_pages": 1,
        }


@router.get("/discover/providers")
async def get_streaming_providers(
    region: str = Query("CH", max_length=2),
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
):
    """Get available streaming providers for a region (featured/major only)."""
    stack = get_stack()
    if not stack.tmdb:
        raise HTTPException(503, "TMDB not configured — set TMDB_API_KEY")
    providers = await stack.tmdb.get_providers(region, media_type)
    return {
        "providers": [
            {
                "id": p.provider_id,
                "name": p.provider_name,
                "logo_url": f"https://image.tmdb.org/t/p/w92{p.logo_path}" if p.logo_path else None,
            }
            for p in providers
        ],
        "region": region,
    }


@router.get("/discover/countries")
async def get_country_options():
    """Get available country options for regional trending."""
    return {"countries": COUNTRY_OPTIONS}


@router.get("/discover/similar/{tmdb_id}")
async def get_similar(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    page: int = Query(1, ge=1),
):
    """Get similar titles to a specific movie/show via TMDB."""
    stack = get_stack()
    similar = await stack.seerr.get_similar(tmdb_id, media_type, page)
    return {
        "results": [
            {
                "tmdb_id": s.tmdb_id,
                "media_type": s.media_type,
                "title": s.title,
                "year": s.year,
                "poster_url": f"https://image.tmdb.org/t/p/w342{s.poster_path}" if s.poster_path else None,
                "vote_average": s.vote_average,
                "genres": stack.seerr.resolve_genre_ids(s.genre_ids, s.media_type),
            }
            for s in similar
        ],
        "seed_tmdb_id": tmdb_id,
        "page": page,
    }


@router.get("/detail/{tmdb_id}")
async def get_detail(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
):
    """Full metadata for a title — keywords, cast, crew, trailers, ratings."""
    stack = get_stack()
    try:
        detail = await stack.seerr.get_detail(tmdb_id, media_type)
    except Exception as e:
        raise HTTPException(404, f"Title not found: {e}")

    return {
        "tmdb_id": detail.tmdb_id,
        "media_type": detail.media_type,
        "title": detail.title,
        "original_title": detail.original_title,
        "year": detail.year,
        "overview": detail.overview,
        "poster_url": f"https://image.tmdb.org/t/p/w500{detail.poster_path}" if detail.poster_path else None,
        "backdrop_url": f"https://image.tmdb.org/t/p/w1280{detail.backdrop_path}" if detail.backdrop_path else None,
        "genres": detail.genres,
        "keywords": detail.keywords,
        "vote_average": detail.vote_average,
        "vote_count": detail.vote_count,
        "runtime": detail.runtime,
        "status": detail.status,
        "original_language": detail.original_language,
        "imdb_id": detail.imdb_id,
        "cast": detail.cast[:10],
        "directors": detail.directors,
        "writers": detail.writers,
        "trailers": detail.trailers,
        "in_library": detail.in_library,
        "media_status": detail.media_status,
    }


# ── Request (Seerr → Radarr/Sonarr) ─────────────────────────────

@router.post("/request/{tmdb_id}")
async def request_media(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    seasons: Optional[str] = None,
):
    """Submit a media request through Seerr → Radarr/Sonarr."""
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
        "request_id": result.request_id,
        "tmdb_id": result.tmdb_id,
        "media_type": result.media_type,
        "status": result.status,
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

    # Resolve TMDB ID → Plex discover GUID (uses admin token for lookup)
    plex_guid = await stack.plex.resolve_plex_guid(tmdb_id, media_type)
    if not plex_guid:
        raise HTTPException(404, f"Could not resolve TMDB {tmdb_id} to Plex metadata")

    # Use the authenticated user's own Plex token for watchlist operation
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

    # Genres from Seerr/TMDB
    all_genres = set()
    try:
        for g in await stack.seerr.get_movie_genres():
            all_genres.add(g.get("name", "") if isinstance(g, dict) else str(g))
    except Exception:
        pass
    try:
        for g in await stack.seerr.get_tv_genres():
            all_genres.add(g.get("name", "") if isinstance(g, dict) else str(g))
    except Exception:
        pass

    # Plex library sections
    libraries = []
    if stack.plex and stack.plex.sections:
        libraries = [
            {"key": s["key"], "title": s["title"], "type": s["type"]}
            for s in stack.plex.sections
        ]

    return {
        "genres": sorted(all_genres - {""}),
        "libraries": libraries,
    }


@router.get("/cache/stats")
async def cache_stats():
    """Cache statistics for monitoring."""
    cache = get_cache()
    return cache.get_stats()


@router.post("/cache/invalidate")
async def invalidate_cache(username: Optional[str] = None):
    """Invalidate cached recommendations.

    - No username: clears all caches
    - With username: clears only that user's caches
    """
    cache = get_cache()
    if username:
        cache.invalidate_user(username)
        return {"status": "ok", "invalidated": username}
    else:
        cache.invalidate_all()
        return {"status": "ok", "invalidated": "all"}
