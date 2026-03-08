"""TMDB discovery and trending endpoints.

Standalone async functions for discover-by-country, discover-by-provider,
new releases, genre discovery, and trending. Each takes a `get_fn` callable
(TMDBClient._get) to avoid coupling to the client instance.
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, Awaitable

from app.clients.tmdb_models import (
    TMDBDiscoverResult,
    StreamingProvider,
    FEATURED_PROVIDERS,
    parse_discover_result,
)

logger = logging.getLogger(__name__)

# Type alias for the TMDB GET function
GetFn = Callable[[str, dict | None], Awaitable[dict]]


async def get_trending(
    get_fn: GetFn,
    media_type: str = "all",
    window: str = "week",
    page: int = 1,
) -> tuple[list[TMDBDiscoverResult], int]:
    """Global trending. media_type: all|movie|tv. window: day|week."""
    d = await get_fn(f"/trending/{media_type}/{window}", {"page": page})
    results = [parse_discover_result(r) for r in d.get("results", [])]
    return results, d.get("total_pages", 1)


async def discover_by_country(
    get_fn: GetFn,
    region: str,
    media_type: str = "movie",
    page: int = 1,
) -> tuple[list[TMDBDiscoverResult], int]:
    """Popular content in a specific country/region."""
    if media_type == "movie":
        d = await get_fn("/discover/movie", {
            "region": region, "sort_by": "popularity.desc",
            "page": page, "vote_count.gte": 10,
        })
    else:
        d = await get_fn("/discover/tv", {
            "watch_region": region, "sort_by": "popularity.desc",
            "page": page, "vote_count.gte": 10,
        })
    results = [parse_discover_result(r, media_type) for r in d.get("results", [])]
    return results, d.get("total_pages", 1)


async def discover_by_provider(
    get_fn: GetFn,
    provider_id: int,
    region: str = "CH",
    media_type: str = "movie",
    page: int = 1,
) -> tuple[list[TMDBDiscoverResult], int]:
    """Popular content on a specific streaming provider in a region."""
    endpoint = "/discover/movie" if media_type == "movie" else "/discover/tv"
    d = await get_fn(endpoint, {
        "watch_region": region, "with_watch_providers": str(provider_id),
        "sort_by": "popularity.desc", "page": page,
    })
    results = [parse_discover_result(r, media_type) for r in d.get("results", [])]
    return results, d.get("total_pages", 1)


async def get_providers(
    get_fn: GetFn,
    region: str = "CH",
    media_type: str = "movie",
) -> list[StreamingProvider]:
    """Get available streaming providers for a region (featured only)."""
    endpoint = f"/watch/providers/{'movie' if media_type == 'movie' else 'tv'}"
    d = await get_fn(endpoint, {"watch_region": region})
    providers = []
    for p in d.get("results", []):
        providers.append(StreamingProvider(
            provider_id=p["provider_id"],
            provider_name=p["provider_name"],
            logo_path=p.get("logo_path"),
            display_priority=p.get("display_priority", 999),
        ))
    featured = [p for p in providers if p.provider_id in FEATURED_PROVIDERS]
    featured.sort(key=lambda p: p.display_priority)
    return featured


async def discover_new_releases(
    get_fn: GetFn,
    days: int = 90,
    media_type: str = "movie",
    page: int = 1,
) -> tuple[list[TMDBDiscoverResult], int]:
    """Recently released content sorted by popularity."""
    now = datetime.utcnow()
    date_from = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")
    if media_type == "movie":
        d = await get_fn("/discover/movie", {
            "sort_by": "popularity.desc",
            "primary_release_date.gte": date_from,
            "primary_release_date.lte": date_to,
            "page": page, "vote_count.gte": 5,
        })
    else:
        d = await get_fn("/discover/tv", {
            "sort_by": "popularity.desc",
            "first_air_date.gte": date_from,
            "first_air_date.lte": date_to,
            "page": page, "vote_count.gte": 5,
        })
    results = [parse_discover_result(r, media_type) for r in d.get("results", [])]
    return results, d.get("total_pages", 1)


async def discover_by_genre(
    get_fn: GetFn,
    genre_id: int,
    media_type: str = "movie",
    page: int = 1,
) -> list[TMDBDiscoverResult]:
    """Discover popular titles by genre."""
    endpoint = "/discover/movie" if media_type == "movie" else "/discover/tv"
    d = await get_fn(endpoint, {
        "with_genres": str(genre_id), "sort_by": "popularity.desc",
        "page": page, "vote_count.gte": 10,
    })
    return [parse_discover_result(r, media_type) for r in d.get("results", [])]


async def discover_upcoming(
    get_fn: GetFn,
    media_type: str = "movie",
    days_ahead: int = 90,
    page: int = 1,
) -> tuple[list[TMDBDiscoverResult], int]:
    """Upcoming releases — movies and TV premiering in the next N days."""
    now = datetime.utcnow()
    date_from = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    if media_type == "movie":
        d = await get_fn("/discover/movie", {
            "sort_by": "primary_release_date.asc",
            "primary_release_date.gte": date_from,
            "primary_release_date.lte": date_to,
            "page": page,
            "vote_count.gte": 0,
            "with_release_type": "2|3",  # theatrical + digital
        })
    else:
        d = await get_fn("/discover/tv", {
            "sort_by": "first_air_date.asc",
            "first_air_date.gte": date_from,
            "first_air_date.lte": date_to,
            "page": page,
            "vote_count.gte": 0,
        })
    results = [parse_discover_result(r, media_type) for r in d.get("results", [])]
    return results, d.get("total_pages", 1)


async def discover_recent(
    get_fn: GetFn,
    media_type: str = "movie",
    days_back: int = 30,
) -> list[dict]:
    """Recently released titles — movies/TV that came out in the last N days.

    Returns raw dicts (not TMDBDiscoverResult) for direct use in calendar.
    """
    now = datetime.utcnow()
    date_from = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")
    if media_type == "movie":
        d = await get_fn("/discover/movie", {
            "sort_by": "primary_release_date.desc",
            "primary_release_date.gte": date_from,
            "primary_release_date.lte": date_to,
            "page": 1,
            "vote_count.gte": 10,
            "with_release_type": "2|3",
        })
    else:
        d = await get_fn("/discover/tv", {
            "sort_by": "first_air_date.desc",
            "first_air_date.gte": date_from,
            "first_air_date.lte": date_to,
            "page": 1,
            "vote_count.gte": 5,
        })
    items = []
    for r in d.get("results", []):
        tmdb_id = r.get("id")
        if not tmdb_id:
            continue
        rd = r.get("release_date") or r.get("first_air_date")
        poster = r.get("poster_path")
        items.append({
            "tmdb_id": tmdb_id,
            "title": r.get("title") or r.get("name") or "Unknown",
            "release_date": rd,
            "media_type": media_type,
            "poster": f"https://image.tmdb.org/t/p/w300{poster}" if poster else None,
            "overview": r.get("overview", ""),
            "vote_average": r.get("vote_average", 0),
            "popularity": r.get("popularity", 0),
            "source": "tmdb",
            "monitored": False,
        })
    return items
