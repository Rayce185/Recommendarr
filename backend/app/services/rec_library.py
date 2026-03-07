"""Library candidate loading and TMDB data helpers.

Functions that interact with Radarr, Sonarr, Seerr, and TMDB clients
to collect and transform candidate data for scoring.
"""

import logging
from typing import Optional

from app.services.cache import get_cache
from app.services.rec_types import Recommendation
from app.utils.genres import normalize_genres

logger = logging.getLogger(__name__)


async def get_library_candidates(
    radarr, sonarr_tv, sonarr_anime, domain: str = "all"
) -> list[dict]:
    """Collect all library items from Radarr/Sonarr as candidate dicts."""
    cache = get_cache()
    cached = cache.get_library(domain)
    if cached is not None:
        return cached

    candidates = []

    if domain in ("all", "movies"):
        movies = await radarr.get_all_movies()
        for m in movies:
            if not m.tmdb_id:
                continue
            candidates.append({
                "tmdb_id": m.tmdb_id,
                "media_type": "movie",
                "title": m.title,
                "year": m.year,
                "genres": normalize_genres(
                    m.genres,
                    original_language=m.original_language if hasattr(m, 'original_language') else None,
                ),
                "overview": m.overview,
                "vote_average": m.vote_average,
                "runtime": m.runtime_minutes,
                "original_language": m.original_language if hasattr(m, 'original_language') else None,
                "poster_path": m.poster_path,
                "imdb_id": m.imdb_id,
                "in_library": True,
                "quality": m.quality if hasattr(m, 'quality') else None,
                "keywords": [],
                "directors": [],
                "cast": [],
                "popularity": m.popularity if hasattr(m, 'popularity') else 0,
            })

    if domain in ("all", "tv"):
        series = await sonarr_tv.get_all_series()
        for s in series:
            if not s.tmdb_id:
                continue
            candidates.append({
                "tmdb_id": s.tmdb_id,
                "media_type": "tv",
                "title": s.title,
                "year": s.year,
                "genres": normalize_genres(
                    s.genres,
                    original_language=s.original_language if hasattr(s, 'original_language') else None,
                ),
                "overview": s.overview,
                "vote_average": s.vote_average,
                "runtime": s.runtime_minutes if hasattr(s, 'runtime_minutes') else None,
                "poster_path": s.poster_path,
                "in_library": True,
                "keywords": [],
                "directors": [],
                "cast": [],
                "popularity": 0,
            })

    if domain in ("all", "anime"):
        anime = await sonarr_anime.get_all_series()
        for s in anime:
            if not s.tmdb_id:
                continue
            candidates.append({
                "tmdb_id": s.tmdb_id,
                "media_type": "tv",
                "title": s.title,
                "year": s.year,
                "genres": normalize_genres(s.genres, is_anime_source=True),
                "overview": s.overview,
                "vote_average": s.vote_average,
                "runtime": s.runtime_minutes if hasattr(s, 'runtime_minutes') else None,
                "poster_path": s.poster_path,
                "in_library": True,
                "keywords": ["anime"],
                "directors": [],
                "cast": [],
                "popularity": 0,
            })

    fix_poster_urls(candidates)
    cache.set_library(domain, candidates)
    return candidates


def fix_poster_urls(candidates: list[dict]) -> None:
    """Replace TVDB poster URLs with TMDB paths from cache.

    Sonarr returns TVDB poster URLs which get hotlink-blocked in browsers.
    Bulk lookup against tmdb_cache and swap for TMDB paths.
    """
    needs_fix = [c for c in candidates
                 if (c.get("poster_path") or "").startswith("http")
                 and "image.tmdb.org" not in (c.get("poster_path") or "")]
    if not needs_fix:
        return

    try:
        from app.database import get_db
        from app.models import TmdbCache
        from sqlalchemy import select

        tmdb_ids = [c["tmdb_id"] for c in needs_fix]
        with get_db() as db:
            rows = db.execute(
                select(TmdbCache.tmdb_id, TmdbCache.poster_path).where(
                    TmdbCache.tmdb_id.in_(tmdb_ids),
                    TmdbCache.poster_path.isnot(None),
                    TmdbCache.poster_path != "",
                )
            ).all()
            poster_map = {r.tmdb_id: r.poster_path for r in rows
                          if r.poster_path and r.poster_path.startswith("/")}

        fixed = 0
        for c in needs_fix:
            tmdb_poster = poster_map.get(c["tmdb_id"])
            if tmdb_poster:
                c["poster_path"] = tmdb_poster
                fixed += 1

        still_broken = len(needs_fix) - fixed
        if fixed or still_broken:
            logger.info(f"Poster fix: {fixed} TVDB→TMDB, {still_broken} need enrichment")
    except Exception as e:
        logger.warning(f"Poster URL fix failed: {e}")


async def get_library_tmdb_ids(radarr, sonarr_tv, sonarr_anime, domain: str = "all") -> set[int]:
    """Get set of all TMDB IDs in the library (for dedup in grab mode)."""
    candidates = await get_library_candidates(radarr, sonarr_tv, sonarr_anime, domain)
    return {c["tmdb_id"] for c in candidates if c.get("tmdb_id")}


async def resolve_genre_ids(
    genre_ids: list[int], media_type: str, tmdb=None, seerr=None, genre_cache: dict = None
) -> list[str]:
    """Resolve TMDB genre IDs to names using TMDB API (with caching)."""
    if tmdb:
        if genre_cache is not None and media_type not in genre_cache:
            try:
                if media_type == "movie":
                    genres = await tmdb.get_movie_genres()
                else:
                    genres = await tmdb.get_tv_genres()
                genre_cache[media_type] = {g["id"]: g["name"] for g in genres}
            except Exception:
                genre_cache[media_type] = {}
        cache = genre_cache or {}
        return [cache.get(media_type, {}).get(gid, f"Genre:{gid}") for gid in genre_ids
                if gid in cache.get(media_type, {})]
    if seerr:
        return seerr.resolve_genre_ids(genre_ids, media_type)
    return []


async def get_detail(tmdb_id: int, media_type: str, tmdb=None, seerr=None) -> dict:
    """Get detail from TMDB (preferred) or Seerr, returning a normalized dict."""
    if tmdb:
        d = await tmdb.get_detail(tmdb_id, media_type)
        return {
            "title": d.get("title", ""),
            "year": d.get("year"),
            "poster_path": d.get("poster_path"),
            "backdrop_path": d.get("backdrop_path"),
            "genres": d.get("genres", []),
            "keywords": d.get("keywords", []),
            "overview": d.get("overview", ""),
            "vote_average": d.get("vote_average", 0),
            "runtime": d.get("runtime"),
            "original_language": d.get("original_language"),
            "directors": [c["name"] for c in d.get("crew", []) if c.get("job") == "Director"],
            "cast": d.get("cast", []),
            "trailers": [],
        }
    detail = await seerr.get_detail(tmdb_id, media_type)
    return {
        "title": detail.title,
        "year": detail.year,
        "poster_path": detail.poster_path,
        "backdrop_path": detail.backdrop_path,
        "genres": normalize_genres(
            detail.genres,
            original_language=getattr(detail, 'original_language', None),
        ),
        "keywords": detail.keywords,
        "overview": detail.overview,
        "vote_average": detail.vote_average,
        "runtime": detail.runtime,
        "original_language": detail.original_language,
        "directors": detail.directors,
        "cast": detail.cast,
        "trailers": detail.trailers if hasattr(detail, "trailers") else [],
    }


async def discover_to_candidate(item, source: str, resolver=None) -> dict:
    """Convert Seerr/TMDB discover result to candidate dict."""
    genres = []
    if resolver and hasattr(item, 'genre_ids'):
        genres = await resolver(item.genre_ids, item.media_type)
    elif hasattr(item, 'genres'):
        genres = item.genres
    return {
        "tmdb_id": item.tmdb_id,
        "media_type": item.media_type,
        "title": item.title,
        "year": item.year,
        "genres": normalize_genres(
            genres, original_language=getattr(item, 'original_language', None)
        ),
        "overview": item.overview,
        "vote_average": item.vote_average,
        "poster_path": item.poster_path,
        "in_library": False,
        "source": source,
        "keywords": [],
        "directors": [],
        "cast": [],
        "popularity": item.popularity,
        "runtime": None,
        "original_language": None,
    }


def candidate_to_recommendation(
    candidate: dict, score: float, breakdown: dict,
    signals: list[str], mode: str
) -> Recommendation:
    """Convert a scored candidate dict to a Recommendation object."""
    return Recommendation(
        tmdb_id=candidate.get("tmdb_id", 0),
        media_type=candidate.get("media_type", "movie"),
        title=candidate.get("title", ""),
        year=candidate.get("year"),
        poster_path=candidate.get("poster_path"),
        backdrop_path=candidate.get("backdrop_path"),
        genres=candidate.get("genres", []),
        keywords=candidate.get("keywords", [])[:10],
        overview=candidate.get("overview"),
        vote_average=candidate.get("vote_average", 0),
        runtime=candidate.get("runtime"),
        original_language=candidate.get("original_language"),
        score=score,
        score_breakdown=breakdown,
        explanation=" · ".join(signals) if signals else "",
        explanation_signals=signals,
        mode=mode,
        in_library=candidate.get("in_library", False),
        quality=candidate.get("quality"),
        source=candidate.get("source"),
        directors=candidate.get("directors", []),
        cast=candidate.get("cast", []),
        trailer_key=candidate.get("trailer_key"),
        trailer_site=candidate.get("trailer_site"),
    )
