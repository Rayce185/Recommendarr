"""Shared helpers for recommendation API routes.

Provides TMDB genre cache, image URL builder, and Recommendation serializer
used across all recommendation sub-modules.
"""

from app.services.recommender import Recommendation
from app.services.factory import get_stack
from app.config import settings
from app.utils.genres import normalize_genres


# Module-level TMDB genre cache (populated on first use)
_tmdb_genre_cache: dict[int, str] = {}


async def ensure_genre_cache():
    global _tmdb_genre_cache
    if _tmdb_genre_cache:
        return
    stack = get_stack()
    if stack.tmdb:
        try:
            for g in await stack.tmdb.get_movie_genres():
                _tmdb_genre_cache[g["id"]] = g["name"]
            for g in await stack.tmdb.get_tv_genres():
                _tmdb_genre_cache[g["id"]] = g["name"]
        except Exception:
            pass


def get_genre_cache() -> dict[int, str]:
    return _tmdb_genre_cache


def resolve_genres(genre_ids: list[int]) -> list[str]:
    return [_tmdb_genre_cache[gid] for gid in genre_ids if gid in _tmdb_genre_cache]


def img_url(path: str | None, size: str = "w342") -> str | None:
    """Build TMDB image URL, handling both relative paths and absolute URLs."""
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"https://image.tmdb.org/t/p/{size}{path}"


def rec_to_dict(r: Recommendation, plex=None) -> dict:
    """Serialize a Recommendation to API response format."""
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
        "poster_url": img_url(r.poster_path, "w342"),
        "backdrop_url": img_url(r.backdrop_path, "w1280"),
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
