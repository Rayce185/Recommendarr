"""Browse & search — TMDB search/discover with library context."""

import logging
from fastapi import APIRouter, Query
from app.services.factory import get_stack
from app.clients.tmdb_models import parse_discover_result

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/browse/genres")
async def get_genres():
    """Return all movie + TV genre IDs/names for filter UI."""
    stack = get_stack()
    if not stack.tmdb:
        return {"movie_genres": [], "tv_genres": []}
    movie_genres = await stack.tmdb.get_movie_genres()
    tv_genres = await stack.tmdb.get_tv_genres()
    return {"movie_genres": movie_genres, "tv_genres": tv_genres}


@router.get("/browse/search")
async def browse_search(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1, le=50),
):
    """Multi-search (movie + TV) via TMDB — returns results with library status."""
    stack = get_stack()
    if not stack.tmdb:
        return {"results": [], "query": q, "page": page}

    raw = await stack.tmdb.search(q, page=page)
    results = []
    for r in raw:
        tmdb_id = r.tmdb_id
        media_type = r.media_type
        label = "movie" if media_type == "movie" else "show"
        in_library = bool(stack.plex._tmdb_map.get(f"{label}:{tmdb_id}")) if stack.plex else False
        is_watched = stack.plex.is_watched(tmdb_id, media_type) if (stack.plex and in_library) else False
        results.append({
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": r.title,
            "year": r.year,
            "poster_url": f"https://image.tmdb.org/t/p/w342{r.poster_path}" if r.poster_path else None,
            "vote_average": r.vote_average,
            "popularity": r.popularity,
            "overview": getattr(r, "overview", ""),
            "in_library": in_library,
            "is_watched": is_watched,
        })
    return {"results": results, "query": q, "page": page}


@router.get("/browse/discover")
async def browse_discover(
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    genre_id: int | None = Query(None, description="TMDB genre ID"),
    year_min: int | None = Query(None, ge=1900, le=2030),
    year_max: int | None = Query(None, ge=1900, le=2030),
    sort_by: str = Query("popularity.desc", description="TMDB sort field"),
    page: int = Query(1, ge=1, le=50),
):
    """Discover titles via TMDB with genre/year filters + library status."""
    stack = get_stack()
    if not stack.tmdb:
        return {"results": [], "page": page}

    params = {
        "sort_by": sort_by,
        "page": page,
        "vote_count.gte": 10,
    }
    if genre_id:
        params["with_genres"] = str(genre_id)
    if year_min:
        key = "primary_release_date.gte" if media_type == "movie" else "first_air_date.gte"
        params[key] = f"{year_min}-01-01"
    if year_max:
        key = "primary_release_date.lte" if media_type == "movie" else "first_air_date.lte"
        params[key] = f"{year_max}-12-31"

    endpoint = f"/discover/{media_type}"
    d = await stack.tmdb._get(endpoint, params)
    raw = d.get("results", [])
    total_pages = d.get("total_pages", 1)
    total_results = d.get("total_results", 0)

    results = []
    for r in raw:
        parsed = parse_discover_result(r, media_type)
        tmdb_id = parsed.tmdb_id
        label = "movie" if media_type == "movie" else "show"
        in_library = bool(stack.plex._tmdb_map.get(f"{label}:{tmdb_id}")) if stack.plex else False
        is_watched = stack.plex.is_watched(tmdb_id, media_type) if (stack.plex and in_library) else False
        results.append({
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": parsed.title,
            "year": parsed.year,
            "poster_url": f"https://image.tmdb.org/t/p/w342{parsed.poster_path}" if parsed.poster_path else None,
            "vote_average": parsed.vote_average,
            "popularity": parsed.popularity,
            "in_library": in_library,
            "is_watched": is_watched,
        })

    return {
        "results": results,
        "page": page,
        "total_pages": min(total_pages, 50),
        "total_results": total_results,
        "media_type": media_type,
    }
