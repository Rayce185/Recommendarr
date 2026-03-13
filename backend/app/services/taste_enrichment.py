"""TMDB metadata enrichment for taste profiling.

Provides enrichment of watch history items with genre, keyword, and
personnel data. Uses a two-phase strategy: SQLite cache first, then
TMDB API for cache misses, with parallel fetching and persistence.
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def enrich_items(
    by_item: dict[str, list],
    tmdb_client: Any | None = None,
    seerr_client: Any | None = None,
    max_enrich: int = 100,
) -> dict[str, dict]:
    """Enrich watch history items with TMDB metadata.

    Two-phase strategy:
      1. Check SQLite TmdbCache for cached metadata
      2. Fetch misses from TMDB API (parallel, semaphore-limited)
      3. Persist API results back to SQLite cache

    Args:
        by_item: Dict of item_key → list of watch events (from Tautulli)
        tmdb_client: Optional TMDBClient for direct API access
        seerr_client: Optional SeerrClient as fallback
        max_enrich: Max titles to enrich (rate limit control)

    Returns:
        Dict of item_key → metadata dict with keys:
            genres, keywords, cast, directors, original_language
    """
    enrich_cache: dict[str, dict] = {}

    # Sort candidates by watch count (most-watched first)
    candidates = []
    for item_key, events in by_item.items():
        primary = events[0]
        tmdb_id = primary.tmdb_id
        if tmdb_id:
            media_type = "movie" if primary.media_type == "movie" else "tv"
            candidates.append((item_key, tmdb_id, media_type, len(events)))
    candidates.sort(key=lambda x: x[3], reverse=True)
    enrich_items_list = [
        (ik, tid, mt) for ik, tid, mt, _ in candidates[:max_enrich]
    ]

    # Phase 1: Check SQLite cache
    cache_hits = 0
    cache_misses = []
    try:
        from app.database import get_db
        from app.models import TmdbCache
        from sqlalchemy import select, and_

        with get_db() as db:
            for ik, tid, mt in enrich_items_list:
                row = db.execute(
                    select(TmdbCache).where(
                        and_(TmdbCache.tmdb_id == tid, TmdbCache.media_type == mt)
                    )
                ).scalar_one_or_none()
                if row and row.genres:
                    genres = row.genres if isinstance(row.genres, list) else json.loads(row.genres) if row.genres else []
                    keywords = row.keywords if isinstance(row.keywords, list) else json.loads(row.keywords) if row.keywords else []
                    cast_crew = row.cast_crew if isinstance(row.cast_crew, dict) else json.loads(row.cast_crew) if row.cast_crew else {}
                    enrich_cache[ik] = {
                        "genres": genres,
                        "keywords": keywords,
                        "cast": cast_crew.get("cast", [])[:5],
                        "directors": cast_crew.get("directors", []),
                        "original_language": row.original_language,
                    }
                    cache_hits += 1
                else:
                    cache_misses.append((ik, tid, mt))
    except Exception as e:
        logger.debug(f"SQLite cache read failed: {e}")
        cache_misses = enrich_items_list

    # Phase 2: Fetch misses from TMDB API (parallel)
    api_fetched = 0
    if cache_misses:
        sem = asyncio.Semaphore(20)

        async def fetch_and_store(ik: str, tid: str, mt: str) -> tuple[str, dict]:
            async with sem:
                return await _fetch_single(ik, tid, mt, tmdb_client, seerr_client)

        tasks = [fetch_and_store(ik, tid, mt) for ik, tid, mt in cache_misses]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, tuple) and r[1]:
                enrich_cache[r[0]] = r[1]
                api_fetched += 1

    logger.info(
        f"Enriched {len(enrich_cache)} titles "
        f"({cache_hits} cached, {api_fetched} from TMDB API)"
    )
    return enrich_cache


async def _fetch_single(
    item_key: str,
    tmdb_id: str,
    media_type: str,
    tmdb_client: Any | None,
    seerr_client: Any | None,
) -> tuple[str, dict]:
    """Fetch metadata for a single item and persist to SQLite cache."""
    try:
        if tmdb_client:
            d = await tmdb_client.get_detail(tmdb_id, media_type)
            result = {
                "genres": d.get("genres", []),
                "keywords": d.get("keywords", []),
                "cast": [c["name"] for c in d.get("cast", [])[:5]],
                "directors": [
                    c["name"] for c in d.get("crew", [])
                    if c.get("job") == "Director"
                ],
                "original_language": d.get("original_language"),
            }
            # Persist to SQLite cache
            _persist_to_cache(tmdb_id, media_type, d, result)
            return item_key, result
        elif seerr_client:
            d = await seerr_client.get_detail(tmdb_id, media_type)
            return item_key, {
                "genres": d.genres,
                "keywords": d.keywords,
                "cast": [c["name"] for c in d.cast[:5]],
                "directors": d.directors,
                "original_language": None,
            }
    except Exception:
        pass
    return item_key, {}


def _persist_to_cache(
    tmdb_id: str,
    media_type: str,
    raw_detail: dict,
    parsed_result: dict,
) -> None:
    """Write enrichment result back to SQLite TmdbCache. Non-fatal on failure."""
    try:
        from app.database import get_db
        from app.models import TmdbCache
        from sqlalchemy import select, and_

        with get_db() as db:
            existing = db.execute(
                select(TmdbCache).where(
                    and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                )
            ).scalar_one_or_none()
            if existing:
                existing.genres = json.dumps(raw_detail.get("genres", []))
                existing.keywords = json.dumps(raw_detail.get("keywords", []))
                existing.cast_crew = json.dumps({
                    "cast": parsed_result["cast"],
                    "directors": parsed_result["directors"],
                })
                existing.title = raw_detail.get("title", "")
                existing.year = raw_detail.get("year")
                existing.overview = raw_detail.get("overview", "")
                existing.vote_average = raw_detail.get("vote_average", 0)
            else:
                db.add(TmdbCache(
                    tmdb_id=tmdb_id, media_type=media_type,
                    title=raw_detail.get("title", ""),
                    year=raw_detail.get("year"),
                    genres=json.dumps(raw_detail.get("genres", [])),
                    keywords=json.dumps(raw_detail.get("keywords", [])),
                    cast_crew=json.dumps({
                        "cast": parsed_result["cast"],
                        "directors": parsed_result["directors"],
                    }),
                    overview=raw_detail.get("overview", ""),
                    vote_average=raw_detail.get("vote_average", 0),
                    poster_path=raw_detail.get("poster_path"),
                    backdrop_path=raw_detail.get("backdrop_path"),
                    original_language=raw_detail.get("original_language"),
                ))
            db.commit()
    except Exception:
        pass  # Cache write failure is non-fatal
