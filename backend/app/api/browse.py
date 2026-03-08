"""Browse & search — TMDB search/discover with library context."""

import asyncio
import logging
from fastapi import APIRouter, Query
from app.services.factory import get_stack
from app.clients.tmdb_models import parse_discover_result

logger = logging.getLogger(__name__)
router = APIRouter()


def _enrich_result(item: dict, stack) -> dict:
    """Add library_name to a browse result dict using Plex section map."""
    if stack.plex:
        item["library_name"] = stack.plex.get_section_name(
            item["tmdb_id"], item["media_type"]
        )
    else:
        item["library_name"] = None
    return item


@router.get("/browse/libraries")
async def get_libraries():
    """Return available Plex library sections for the filter UI."""
    stack = get_stack()
    if not stack.plex:
        return {"libraries": []}
    sections = stack.plex.sections
    return {
        "libraries": [
            {"key": s["key"], "title": s["title"], "type": s["type"]}
            for s in sections
        ]
    }


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
    library: str | None = Query(None, description="Filter to Plex library name"),
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
        item = {
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
        }
        _enrich_result(item, stack)
        # Library filter: skip items not in the requested library
        if library and item.get("library_name") != library:
            continue
        results.append(item)
    return {"results": results, "query": q, "page": page}


async def _discover_one(stack, media_type: str, params: dict) -> tuple:
    """Run a single TMDB discover call and return (results, total_pages, total_results)."""
    # Adjust date keys for media type
    p = dict(params)
    endpoint = f"/discover/{media_type}"
    d = await stack.tmdb._get(endpoint, p)
    raw = d.get("results", [])
    results = []
    for r in raw:
        parsed = parse_discover_result(r, media_type)
        tmdb_id = parsed.tmdb_id
        label = "movie" if media_type == "movie" else "show"
        in_library = bool(stack.plex._tmdb_map.get(f"{label}:{tmdb_id}")) if stack.plex else False
        is_watched = stack.plex.is_watched(tmdb_id, media_type) if (stack.plex and in_library) else False
        item = {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": parsed.title,
            "year": parsed.year,
            "poster_url": f"https://image.tmdb.org/t/p/w342{parsed.poster_path}" if parsed.poster_path else None,
            "vote_average": parsed.vote_average,
            "popularity": parsed.popularity,
            "in_library": in_library,
            "is_watched": is_watched,
        }
        _enrich_result(item, stack)
        results.append(item)
    return results, d.get("total_pages", 1), d.get("total_results", 0)


@router.get("/browse/discover")
async def browse_discover(
    media_type: str = Query("movie", pattern="^(movie|tv|all)$"),
    genre_id: int | None = Query(None, description="TMDB genre ID"),
    year_min: int | None = Query(None, ge=1900, le=2030),
    year_max: int | None = Query(None, ge=1900, le=2030),
    sort_by: str = Query("popularity.desc", description="TMDB sort field"),
    page: int = Query(1, ge=1, le=50),
    library: str | None = Query(None, description="Filter to Plex library name"),
):
    """Discover titles via TMDB with genre/year filters + library status.

    media_type=all fetches both movies and TV in parallel, merged by popularity.
    """
    stack = get_stack()
    if not stack.tmdb:
        return {"results": [], "page": page}

    base_params = {
        "sort_by": sort_by,
        "page": page,
        "vote_count.gte": 10,
    }
    if genre_id:
        base_params["with_genres"] = str(genre_id)

    if media_type == "all":
        # Parallel discover for movie + tv
        movie_params = dict(base_params)
        tv_params = dict(base_params)
        if year_min:
            movie_params["primary_release_date.gte"] = f"{year_min}-01-01"
            tv_params["first_air_date.gte"] = f"{year_min}-01-01"
        if year_max:
            movie_params["primary_release_date.lte"] = f"{year_max}-12-31"
            tv_params["first_air_date.lte"] = f"{year_max}-12-31"

        (m_results, m_pages, m_total), (t_results, t_pages, t_total) = await asyncio.gather(
            _discover_one(stack, "movie", movie_params),
            _discover_one(stack, "tv", tv_params),
        )

        # Merge and sort by popularity (descending)
        combined = m_results + t_results
        combined.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        # Take top 20 per page (standard TMDB page size)
        results = combined[:20]
        total_pages = max(m_pages, t_pages)
        total_results = m_total + t_total
    else:
        # Single media type discover
        params = dict(base_params)
        if year_min:
            key = "primary_release_date.gte" if media_type == "movie" else "first_air_date.gte"
            params[key] = f"{year_min}-01-01"
        if year_max:
            key = "primary_release_date.lte" if media_type == "movie" else "first_air_date.lte"
            params[key] = f"{year_max}-12-31"
        results, total_pages, total_results = await _discover_one(stack, media_type, params)

    # Apply library filter
    if library:
        results = [r for r in results if r.get("library_name") == library]

    return {
        "results": results,
        "page": page,
        "total_pages": min(total_pages, 50),
        "total_results": total_results,
        "media_type": media_type,
    }
