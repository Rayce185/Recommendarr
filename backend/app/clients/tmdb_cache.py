"""TMDB SQLite cache layer — read/write for detail data.

Provides persistence for TMDB API responses to avoid redundant API calls.
Cache entries include a schema version check (v2: trailers, networks fields).
Non-fatal on all errors — cache is convenience, not correctness.
"""

import json
import logging

logger = logging.getLogger(__name__)


def read_cache(tmdb_id: int, media_type: str) -> dict | None:
    """Read from SQLite tmdb_cache table. Returns parsed detail dict or None."""
    try:
        from app.database import get_db
        from app.models import TmdbCache
        from sqlalchemy import select, and_

        with get_db() as db:
            row = db.execute(
                select(TmdbCache).where(
                    and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                )
            ).scalar_one_or_none()
            if not row or not row.genres:
                return None

            cast_crew_raw = (
                row.cast_crew if isinstance(row.cast_crew, dict)
                else json.loads(row.cast_crew) if row.cast_crew else {}
            )
            # Schema v2 check — force re-fetch if trailers field missing
            if "trailers" not in cast_crew_raw:
                return None

            genres = row.genres if isinstance(row.genres, list) else json.loads(row.genres) if row.genres else []
            keywords = row.keywords if isinstance(row.keywords, list) else json.loads(row.keywords) if row.keywords else []
            cc = cast_crew_raw

            return {
                "tmdb_id": tmdb_id,
                "media_type": media_type,
                "title": row.title or "",
                "original_title": row.original_title or "",
                "year": row.year,
                "overview": row.overview or "",
                "poster_path": row.poster_path,
                "backdrop_path": row.backdrop_path,
                "vote_average": float(row.vote_average) if row.vote_average else 0,
                "vote_count": cc.get("vote_count", 0),
                "popularity": float(row.popularity) if row.popularity else 0,
                "genres": genres,
                "keywords": keywords,
                "cast": cc.get("cast", []),
                "crew": cc.get("crew", []),
                "directors": cc.get("directors", []),
                "runtime": row.runtime_minutes,
                "original_language": row.original_language,
                "imdb_id": cc.get("imdb_id"),
                "tvdb_id": cc.get("tvdb_id"),
                "tagline": cc.get("tagline", ""),
                "production_companies": cc.get("production_companies", []),
                "networks": cc.get("networks", []),
                "trailers": cc.get("trailers", []),
                "episode_runtime": cc.get("episode_runtime"),
                "last_air_date": cc.get("last_air_date", ""),
                "number_of_seasons": cc.get("number_of_seasons"),
                "number_of_episodes": cc.get("number_of_episodes"),
                "release_date": cc.get("release_date", ""),
                "status": cc.get("status"),
                "content_rating": "",
            }
    except Exception:
        pass
    return None


def write_cache(tmdb_id: int, media_type: str, data: dict) -> None:
    """Write to SQLite tmdb_cache table. Fire-and-forget, non-fatal."""
    try:
        from app.database import get_db
        from app.models import TmdbCache
        from sqlalchemy import select, and_

        cast_crew = {
            "cast": [c["name"] if isinstance(c, dict) else c for c in data.get("cast", [])[:10]],
            "crew": [
                {"name": c["name"], "job": c["job"]}
                for c in data.get("crew", []) if isinstance(c, dict)
            ],
            "directors": data.get("directors", []) if isinstance(data.get("directors"), list) else [],
            "imdb_id": data.get("imdb_id"),
            "tvdb_id": data.get("tvdb_id"),
            "tagline": data.get("tagline", ""),
            "production_companies": data.get("production_companies", []),
            "networks": data.get("networks", []),
            "trailers": data.get("trailers", []),
            "episode_runtime": data.get("episode_runtime"),
            "last_air_date": data.get("last_air_date", ""),
            "number_of_seasons": data.get("number_of_seasons"),
            "number_of_episodes": data.get("number_of_episodes"),
            "release_date": data.get("release_date", ""),
            "status": data.get("status"),
            "vote_count": data.get("vote_count", 0),
        }

        with get_db() as db:
            existing = db.execute(
                select(TmdbCache).where(
                    and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                )
            ).scalar_one_or_none()
            if existing:
                existing.title = data.get("title", "")
                existing.year = data.get("year")
                existing.genres = json.dumps(data.get("genres", []))
                existing.keywords = json.dumps(data.get("keywords", []))
                existing.cast_crew = json.dumps(cast_crew)
                existing.overview = data.get("overview", "")
                existing.vote_average = data.get("vote_average", 0)
                existing.popularity = data.get("popularity", 0)
                existing.poster_path = data.get("poster_path")
                existing.backdrop_path = data.get("backdrop_path")
                existing.runtime_minutes = data.get("runtime")
                existing.original_language = data.get("original_language")
            else:
                db.add(TmdbCache(
                    tmdb_id=tmdb_id, media_type=media_type,
                    title=data.get("title", ""),
                    original_title=data.get("original_title", ""),
                    year=data.get("year"),
                    genres=json.dumps(data.get("genres", [])),
                    keywords=json.dumps(data.get("keywords", [])),
                    cast_crew=json.dumps(cast_crew),
                    overview=data.get("overview", ""),
                    vote_average=data.get("vote_average", 0),
                    popularity=data.get("popularity", 0),
                    poster_path=data.get("poster_path"),
                    backdrop_path=data.get("backdrop_path"),
                    runtime_minutes=data.get("runtime"),
                    original_language=data.get("original_language"),
                ))
            db.commit()
    except Exception as e:
        logger.debug(f"TMDB cache write failed for {tmdb_id}: {e}")
