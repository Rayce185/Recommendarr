"""Collection gap detection API routes.

Identifies partially completed movie collections and shows missing parts.
Uses stale-while-revalidate caching for responsive UX.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.services.factory import get_stack, resolve_user_id
from app.services.cache import get_cache, DATA_LAYER_TTL
from app.services.collections import CollectionService
from app.auth.jwt_handler import TokenPayload, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/recommend/{username}/collections")
async def get_collections(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Get partially completed movie collections for a user.

    Uses stale-while-revalidate: returns cached data instantly (even if stale),
    triggers background refresh if data is older than TTL.
    """
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view other users' collections")

    stack = get_stack()
    if not stack.tmdb:
        raise HTTPException(503, "TMDB client not configured — set TMDB_API_KEY")

    # L1: In-memory cache (fastest)
    cache = get_cache()
    cached_colls = cache.get_collections(username)
    if cached_colls is not None:
        return {"username": username, "collections": cached_colls, "total": len(cached_colls), "cached": True}

    # Lazy-init collection service
    if not hasattr(stack, "_collection_svc") or stack._collection_svc is None:
        stack._collection_svc = CollectionService(stack.tmdb, stack.radarr, stack.tautulli)

    # L2: SQLite persistent cache (survives restarts)
    sqlite_data, is_fresh = stack._collection_svc.get_cached_results(username)

    if sqlite_data is not None:
        cache.set_collections(username, sqlite_data)
        if not is_fresh:
            asyncio.create_task(_refresh_collections_bg(username, stack, cache))
        return {"username": username, "collections": sqlite_data, "total": len(sqlite_data), "cached": True, "stale": not is_fresh}

    # L3: Full TMDB scan (cold start — only happens once per user ever)
    try:
        collections = await asyncio.wait_for(
            stack._collection_svc.get_user_collections(username),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        # Start background computation and return empty with flag
        asyncio.create_task(_refresh_collections_bg(username, stack, cache))
        return {"username": username, "collections": [], "total": 0, "computing": True,
                "message": "Collection scan started — reload in a minute for results"}

    coll_list = _format_collections(collections)
    cache.set_collections(username, coll_list)
    stack._collection_svc._persist_results(username, coll_list)

    return {"username": username, "collections": coll_list, "total": len(coll_list)}


def _format_collections(collections):
    """Format UserCollection list into API response dicts."""
    def _fmt_part(p):
        return {
            "tmdb_id": p.tmdb_id, "title": p.title, "year": p.year,
            "poster_url": p.poster_url, "vote_average": p.vote_average,
            "in_library": p.in_library, "watched": p.watched,
            "release_date": p.release_date,
        }
    return [
        {
            "collection_id": c.collection_id, "name": c.name,
            "poster_url": c.poster_url, "backdrop_url": c.backdrop_url,
            "total_parts": c.total_parts, "watched_count": c.watched_count,
            "in_library_count": c.in_library_count, "completion_pct": c.completion_pct,
            "parts": [_fmt_part(p) for p in c.parts],
            "missing": [_fmt_part(p) for p in c.missing_parts],
        }
        for c in collections
    ]


async def _refresh_collections_bg(username: str, stack, cache):
    """Background task: refresh stale collection data."""
    try:
        collections = await stack._collection_svc.get_user_collections(username)
        coll_list = _format_collections(collections)
        cache.set_collections(username, coll_list)
        stack._collection_svc._persist_results(username, coll_list)
        logger.info(f"Background collection refresh complete for {username}: {len(coll_list)} collections")
    except Exception as e:
        logger.warning(f"Background collection refresh failed for {username}: {e}")


@router.get("/collection/for/{tmdb_id}")
async def get_collection_for_movie(
    tmdb_id: int,
    user: TokenPayload = Depends(get_current_user),
):
    """Check if a movie belongs to a collection and return completion status.

    Returns collection info with per-part watched/library status.
    Returns 204 (no content) if the movie is not part of a collection.
    Uses generic cache (5 min TTL) to avoid repeated Radarr/Tautulli calls.
    """
    cache = get_cache()
    cache_key = f"collfor:{user.username}:{tmdb_id}"
    cached = cache.get_generic(cache_key)
    if cached is not None:
        if cached == "__none__":
            from fastapi.responses import Response
            return Response(status_code=204)
        return cached

    stack = get_stack()
    if not stack.tmdb:
        raise HTTPException(503, "TMDB not configured")

    coll_info = await stack.tmdb.get_movie_collection_id(tmdb_id)
    if not coll_info:
        cache.set_generic(cache_key, "__none__", ttl=DATA_LAYER_TTL)
        from fastapi.responses import Response
        return Response(status_code=204)

    coll = await stack.tmdb.get_collection(coll_info["id"])
    if not coll:
        cache.set_generic(cache_key, "__none__", ttl=DATA_LAYER_TTL)
        from fastapi.responses import Response
        return Response(status_code=204)

    # Cross-reference with library + watch status (shared cached sets — 30min TTL)
    library_tmdb = cache.get_generic("_radarr_library_ids")
    if library_tmdb is None:
        movies = await stack.radarr.get_all_movies()
        library_tmdb = [m.tmdb_id for m in movies if m.tmdb_id]
        cache.set_generic("_radarr_library_ids", library_tmdb, ttl=DATA_LAYER_TTL)
    library_tmdb = set(library_tmdb)

    uid = resolve_user_id(user.username)
    watched_key = f"_watched_ids:{user.username}"
    user_watched = cache.get_generic(watched_key)
    if user_watched is None:
        history = await stack.tautulli.get_history(user_id=None, limit=10000)
        user_watched = [e.tmdb_id for e in history if e.user_id == uid and e.media_type == "movie" and e.tmdb_id]
        cache.set_generic(watched_key, user_watched, ttl=DATA_LAYER_TTL)
    user_watched = set(user_watched)

    parts = []
    watched_count = 0
    in_lib_count = 0
    missing = []

    for p in coll["parts"]:
        in_lib = p["tmdb_id"] in library_tmdb
        watched = p["tmdb_id"] in user_watched

        poster = f"https://image.tmdb.org/t/p/w342{p['poster_path']}" if p.get("poster_path") else None
        part = {
            "tmdb_id": p["tmdb_id"],
            "title": p["title"],
            "year": p.get("year"),
            "poster_url": poster,
            "vote_average": p.get("vote_average", 0),
            "in_library": in_lib,
            "watched": watched,
            "release_date": p.get("release_date"),
        }
        parts.append(part)
        if watched:
            watched_count += 1
        if in_lib:
            in_lib_count += 1
        if not in_lib:
            missing.append(part)

    total = len(parts)
    poster_url = f"https://image.tmdb.org/t/p/w342{coll['poster_path']}" if coll.get("poster_path") else None

    result = {
        "collection_id": coll["collection_id"],
        "name": coll["name"],
        "poster_url": poster_url,
        "total_parts": total,
        "watched_count": watched_count,
        "in_library_count": in_lib_count,
        "completion_pct": round((watched_count / total) * 100, 1) if total else 0,
        "current_tmdb_id": tmdb_id,
        "parts": parts,
        "missing": missing,
    }
    cache.set_generic(cache_key, result, ttl=DATA_LAYER_TTL)
    return result
