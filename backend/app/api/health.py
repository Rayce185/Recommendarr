"""Health & system status endpoints v2 — live service probing."""

from fastapi import APIRouter
from datetime import datetime, timezone

from app.services.factory import get_stack

router = APIRouter()


@router.get("/health")
async def health_check():
    """Service health — probes all upstream APIs."""
    stack = get_stack()

    checks = {}

    # Tautulli
    try:
        ok = await stack.tautulli.test_connection()
        checks["tautulli"] = {"status": "ok" if ok else "error", "url": stack.tautulli.url}
    except Exception as e:
        checks["tautulli"] = {"status": "error", "error": str(e)}

    # Seerr
    try:
        ok = await stack.seerr.test_connection()
        checks["seerr"] = {"status": "ok" if ok else "error", "url": stack.seerr.url}
    except Exception as e:
        checks["seerr"] = {"status": "error", "error": str(e)}

    # Radarr
    try:
        ok = await stack.radarr.test_connection()
        checks["radarr"] = {"status": "ok" if ok else "error", "url": stack.radarr.url}
    except Exception as e:
        checks["radarr"] = {"status": "error", "error": str(e)}

    # Sonarr TV
    try:
        ok = await stack.sonarr_tv.test_connection()
        checks["sonarr_tv"] = {"status": "ok" if ok else "error", "url": stack.sonarr_tv.url}
    except Exception as e:
        checks["sonarr_tv"] = {"status": "error", "error": str(e)}

    # Sonarr Anime
    try:
        ok = await stack.sonarr_anime.test_connection()
        checks["sonarr_anime"] = {"status": "ok" if ok else "error", "url": stack.sonarr_anime.url}
    except Exception as e:
        checks["sonarr_anime"] = {"status": "error", "error": str(e)}

    all_ok = all(c.get("status") == "ok" for c in checks.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "0.4.0",
        "architecture": "api-first",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": checks,
        "users_loaded": len(stack.user_map) if stack.user_map else 0,
    }


@router.get("/stats")
async def system_stats():
    """Library statistics from Radarr/Sonarr."""
    stack = get_stack()

    stats = {}
    try:
        movies = await stack.radarr.get_all_movies()
        stats["movies"] = len(movies)
    except Exception:
        stats["movies"] = "error"

    try:
        tv = await stack.sonarr_tv.get_all_series()
        stats["tv_series"] = len(tv)
    except Exception:
        stats["tv_series"] = "error"

    try:
        anime = await stack.sonarr_anime.get_all_series()
        stats["anime_series"] = len(anime)
    except Exception:
        stats["anime_series"] = "error"

    try:
        users = await stack.tautulli.get_users()
        stats["users"] = len([u for u in users if u.get("username")])
    except Exception:
        stats["users"] = "error"

    return stats


@router.get("/genres")
async def get_genres():
    """All available genre lists from TMDB via Seerr."""
    stack = get_stack()

    try:
        movie_genres = await stack.seerr.get_movie_genres()
        tv_genres = await stack.seerr.get_tv_genres()
    except Exception as e:
        return {"error": str(e)}

    return {
        "movie_genres": movie_genres,
        "tv_genres": tv_genres,
    }
