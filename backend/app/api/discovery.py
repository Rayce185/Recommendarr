"""Discovery & browsing API routes.

Trending, similar titles, detail pages, world cinema map, reddit buzz.
All endpoints proxy through TMDB with Seerr fallback.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from app.services.factory import get_stack
from app.services.cache import get_cache
from app.clients.tmdb import COUNTRY_OPTIONS
from app.utils.genres import normalize_genres
from app.api.rec_helpers import ensure_genre_cache, get_genre_cache

logger = logging.getLogger(__name__)
router = APIRouter()


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


# ── Similar & Detail ─────────────────────────────────────────────

@router.get("/discover/similar/{tmdb_id}")
async def get_similar(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    page: int = Query(1, ge=1),
):
    """Get similar titles to a specific movie/show via TMDB."""
    stack = get_stack()
    await ensure_genre_cache()
    genre_cache = get_genre_cache()
    if stack.tmdb:
        similar = await stack.tmdb.get_similar(tmdb_id, media_type, page)
    else:
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
                "genres": normalize_genres([genre_cache.get(gid) for gid in (s.genre_ids if hasattr(s, "genre_ids") else []) if gid in genre_cache], original_language=getattr(s, "original_language", None)) if hasattr(s, "genre_ids") else [],
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
        if stack.tmdb:
            d = await stack.tmdb.get_detail(tmdb_id, media_type)
            label = "movie" if media_type == "movie" else "show"
            in_library = bool(stack.plex._tmdb_map.get(f"{label}:{tmdb_id}")) if stack.plex else False
            wp = await stack.tmdb.get_watch_providers(tmdb_id, media_type, region="CH")
            trailers_raw = d.get("trailers", [])
            trailer_url = f"https://www.youtube.com/embed/{trailers_raw[0]['key']}" if trailers_raw else None
            return {
                "tmdb_id": d["tmdb_id"],
                "media_type": d["media_type"],
                "title": d["title"],
                "original_title": d.get("original_title", ""),
                "year": d.get("year"),
                "overview": d.get("overview", ""),
                "tagline": d.get("tagline", ""),
                "poster_url": f"https://image.tmdb.org/t/p/w500{d['poster_path']}" if d.get("poster_path") else None,
                "backdrop_url": f"https://image.tmdb.org/t/p/w1280{d['backdrop_path']}" if d.get("backdrop_path") else None,
                "genres": normalize_genres(d.get("genres", []), original_language=d.get("original_language")),
                "keywords": d.get("keywords", []),
                "vote_average": d.get("vote_average", 0),
                "vote_count": d.get("vote_count", 0),
                "runtime": d.get("runtime"),
                "episode_runtime": d.get("episode_runtime"),
                "status": d.get("status"),
                "original_language": d.get("original_language"),
                "imdb_id": d.get("imdb_id"),
                "tvdb_id": d.get("tvdb_id"),
                "release_date": d.get("release_date", ""),
                "last_air_date": d.get("last_air_date", ""),
                "number_of_seasons": d.get("number_of_seasons"),
                "number_of_episodes": d.get("number_of_episodes"),
                "production_companies": d.get("production_companies", []),
                "networks": d.get("networks", []),
                "cast": d.get("cast", [])[:10],
                "directors": [c["name"] for c in d.get("crew", []) if c.get("job") == "Director"],
                "writers": [c["name"] for c in d.get("crew", []) if c.get("job") in ("Writer", "Screenplay")],
                "creators": [c["name"] for c in d.get("crew", []) if c.get("job") == "Creator"],
                "trailer_url": trailer_url,
                "trailers": [{"key": t["key"], "name": t["name"]} for t in trailers_raw],
                "watch_providers": wp.get("providers", {}),
                "watch_providers_link": wp.get("link", ""),
                "content_rating": d.get("content_rating", ""),
                "in_library": in_library,
                "media_status": None,
            }
        else:
            detail = await stack.seerr.get_detail(tmdb_id, media_type)
            return {
                "tmdb_id": detail.tmdb_id,
                "media_type": detail.media_type,
                "title": detail.title,
                "original_title": detail.original_title,
                "year": detail.year,
                "overview": detail.overview,
                "poster_url": f"https://image.tmdb.org/t/p/w500{detail.poster_path}" if detail.poster_path else None,
                "backdrop_url": f"https://image.tmdb.org/t/p/w1280{detail.backdrop_path}" if detail.backdrop_path else None,
                "genres": normalize_genres(detail.genres, original_language=getattr(detail, "original_language", None)),
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
    except Exception as e:
        raise HTTPException(404, f"Title not found: {e}")


# ── World Cinema Map ─────────────────────────────────────────────

@router.get("/discover/world-cinema")
async def get_world_cinema_map(
    username: Optional[str] = Query(None, description="Username for taste matching"),
):
    """World cinema map with per-country taste match scores."""
    from app.services.world_cinema import get_world_cinema_map as _get_map

    user_genres = None
    if username:
        try:
            stack = get_stack()
            cache = get_cache()
            profile = cache.get_profile(username, "all")
            if not profile:
                profile = await stack.profiler.build_profile(username=username, domain="all", enrich_keywords=False)
                cache.set_profile(username, "all", profile)
            user_genres = {g.genre: g.score for g in profile.genres}
        except Exception as e:
            logger.warning(f"Could not build taste profile for world cinema: {e}")

    return _get_map(user_genres)


# ── Talk of the Web (Reddit Buzz) ────────────────────────────────

@router.get("/discover/buzz")
async def get_reddit_buzz_endpoint(
    subreddits: Optional[str] = Query(None, description="Comma-separated subreddit names"),
    limit: int = Query(15, ge=5, le=30, description="Posts per subreddit"),
    enrich: bool = Query(True, description="Cross-reference with TMDB"),
):
    """Talk of the Web — Reddit-powered film/TV buzz."""
    from app.services.reddit_buzz import get_reddit_buzz, SOURCES

    stack = get_stack()
    sub_list = subreddits.split(",") if subreddits else None

    items = await get_reddit_buzz(
        seerr_client=stack.seerr,
        subreddits=sub_list,
        limit_per_sub=limit,
        enrich_tmdb=enrich,
    )

    available_subs = [{"name": s["sub"], "label": s["label"], "category": s["category"]} for s in SOURCES]

    return {
        "results": items,
        "total": len(items),
        "sources": available_subs,
    }
