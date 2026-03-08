"""Discovery & browsing API routes.

Trending, similar titles, detail pages, world cinema map, reddit buzz.
All endpoints proxy through TMDB with Seerr fallback.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from app.services.factory import get_stack
from app.clients.tmdb import COUNTRY_OPTIONS
from app.utils.genres import normalize_genres
from app.api.rec_helpers import ensure_genre_cache, get_genre_cache

logger = logging.getLogger(__name__)
router = APIRouter()


async def _both_or_single(stack, media_type, source, **kw):
    """Fetch both movies+TV when media_type='all', else single type."""
    if media_type == "all":
        import asyncio
        if source == "country":
            m_coro = stack.tmdb.discover_by_country(kw["region"], "movie", kw.get("page", 1))
            t_coro = stack.tmdb.discover_by_country(kw["region"], "tv", kw.get("page", 1))
        elif source == "provider":
            m_coro = stack.tmdb.discover_by_provider(kw["provider_id"], kw.get("region", "CH"), "movie", kw.get("page", 1))
            t_coro = stack.tmdb.discover_by_provider(kw["provider_id"], kw.get("region", "CH"), "tv", kw.get("page", 1))
        else:  # new_releases
            m_coro = stack.tmdb.discover_new_releases(kw.get("days", 90), "movie", kw.get("page", 1))
            t_coro = stack.tmdb.discover_new_releases(kw.get("days", 90), "tv", kw.get("page", 1))
        (m_res, m_pages), (t_res, t_pages) = await asyncio.gather(m_coro, t_coro)
        # Interleave by popularity
        combined = sorted(m_res + t_res, key=lambda r: getattr(r, "popularity", 0), reverse=True)
        return combined[:20], max(m_pages, t_pages)
    mt = media_type
    if source == "country":
        return await stack.tmdb.discover_by_country(kw["region"], mt, kw.get("page", 1))
    elif source == "provider":
        return await stack.tmdb.discover_by_provider(kw["provider_id"], kw.get("region", "CH"), mt, kw.get("page", 1))
    else:
        return await stack.tmdb.discover_new_releases(kw.get("days", 90), mt, kw.get("page", 1))



# ── Trending ─────────────────────────────────────────────────────

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
    await ensure_genre_cache()
    genre_cache = get_genre_cache()

    def _fmt(t) -> dict:
        """Format a TMDB result for API response."""
        poster = None
        if t.poster_path:
            poster = f"https://image.tmdb.org/t/p/w342{t.poster_path}" if not t.poster_path.startswith("http") else t.poster_path
        genres = []
        if hasattr(t, "genre_ids") and t.genre_ids:
            genres = [genre_cache.get(gid, f"Genre:{gid}") for gid in t.genre_ids if gid in genre_cache]
        return {
            "tmdb_id": t.tmdb_id,
            "media_type": t.media_type,
            "title": t.title,
            "year": t.year,
            "poster_url": poster,
            "vote_average": t.vote_average,
            "genres": normalize_genres(genres, original_language=t.original_language if hasattr(t, 'original_language') else None),
            "popularity": getattr(t, "popularity", 0),
            "original_language": getattr(t, "original_language", None),
            "release_date": getattr(t, "release_date", None),
        }

    if stack.tmdb:
        if source == "global":
            if media_type == "anime":
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
            results, total_pages = await _both_or_single(
                stack, media_type, "country", region=region, page=page)
        elif source == "provider":
            if not provider_id:
                raise HTTPException(400, "provider_id required for source=provider")
            results, total_pages = await _both_or_single(
                stack, media_type, "provider", region=region, page=page, provider_id=provider_id)
        elif source == "new_releases":
            results, total_pages = await _both_or_single(
                stack, media_type, "new_releases", page=page, days=days)
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
            "total_pages": min(total_pages, 20),
        }
    else:
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
