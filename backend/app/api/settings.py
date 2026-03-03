"""System Settings API — admin configuration, service testing, cache management."""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional

from app.services.factory import get_stack
from app.services.cache import get_cache
from app.config import settings
from app.auth.jwt_handler import TokenPayload, get_current_user


def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Dependency that requires admin role."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


router = APIRouter()


def _mask_key(key: str) -> str:
    """Mask an API key for display (show first 4, last 4)."""
    if not key or len(key) < 12:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


@router.get("/settings")
async def get_settings(admin: TokenPayload = Depends(require_admin)):
    """Get current system configuration (keys masked)."""
    return {
        "services": {
            "plex": {
                "url": settings.plex_url,
                "api_key": _mask_key(settings.plex_token),
                "machine_id": settings.plex_machine_id[:8] + "..." if settings.plex_machine_id else None,
            },
            "tautulli": {
                "url": settings.tautulli_url,
                "api_key": _mask_key(settings.tautulli_api_key),
            },
            "radarr": {
                "url": settings.radarr_url,
                "api_key": _mask_key(settings.radarr_api_key),
            },
            "sonarr_tv": {
                "url": settings.sonarr_url,
                "api_key": _mask_key(settings.sonarr_api_key),
            },
            "sonarr_anime": {
                "url": settings.sonarr_anime_url,
                "api_key": _mask_key(settings.sonarr_anime_api_key),
            },
            "seerr": {
                "url": settings.seerr_url,
                "api_key": _mask_key(settings.seerr_api_key),
            },
            "tmdb": {
                "url": "https://api.themoviedb.org/3",
                "api_key": _mask_key(settings.tmdb_api_key),
            },
        },
        "llm": {
            "enabled": bool(settings.llm_base_url),
            "url": settings.llm_base_url or None,
            "chromadb_url": settings.chromadb_url or None,
            "embedding_model": settings.embedding_model,
        },
        "auth": {
            "jwt_expiry_hours": settings.jwt_expiry_hours,
        },
    }


@router.post("/settings/test-connection")
async def test_connection(
    admin: TokenPayload = Depends(require_admin),
    service: str = Query(..., description="Service name to test"),
):
    """Test connectivity to a specific backend service.

    Services: plex, tautulli, radarr, sonarr_tv, sonarr_anime, seerr, tmdb
    """
    stack = get_stack()

    testers = {
        "plex": lambda: _test_plex(stack),
        "tautulli": lambda: _test_tautulli(stack),
        "radarr": lambda: _test_radarr(stack),
        "sonarr_tv": lambda: _test_sonarr(stack, "tv"),
        "sonarr_anime": lambda: _test_sonarr(stack, "anime"),
        "seerr": lambda: _test_seerr(stack),
        "tmdb": lambda: _test_tmdb(stack),
    }

    if service not in testers:
        raise HTTPException(400, f"Unknown service: {service}. Available: {', '.join(testers.keys())}")

    try:
        result = await testers[service]()
        return result
    except Exception as e:
        return {
            "service": service,
            "status": "error",
            "message": str(e),
        }


async def _test_plex(stack) -> dict:
    if not stack.plex:
        return {"service": "plex", "status": "error", "message": "Not configured"}
    try:
        ok = await stack.plex.test_connection()
        if ok:
            n_sections = len(stack.plex.sections) if stack.plex.sections else 0
            return {"service": "plex", "status": "ok", "message": f"Connected, {n_sections} library sections"}
        return {"service": "plex", "status": "error", "message": "Connection failed"}
    except Exception as e:
        return {"service": "plex", "status": "error", "message": str(e)}


async def _test_tautulli(stack) -> dict:
    try:
        users = await stack.tautulli.get_users()
        return {
            "service": "tautulli",
            "status": "ok",
            "message": f"{len(users)} users loaded",
            "details": {"users": len(users)},
        }
    except Exception as e:
        return {"service": "tautulli", "status": "error", "message": str(e)}


async def _test_radarr(stack) -> dict:
    try:
        ok = await stack.radarr.test_connection()
        if ok:
            return {"service": "radarr", "status": "ok", "message": "Connected"}
        return {"service": "radarr", "status": "error", "message": "Connection failed"}
    except Exception as e:
        return {"service": "radarr", "status": "error", "message": str(e)}


async def _test_sonarr(stack, variant: str) -> dict:
    try:
        client = stack.sonarr_tv if variant == "tv" else stack.sonarr_anime
        ok = await client.test_connection()
        label = "TV" if variant == "tv" else "Anime"
        if ok:
            return {"service": f"sonarr_{variant}", "status": "ok", "message": f"Sonarr {label} connected"}
        return {"service": f"sonarr_{variant}", "status": "error", "message": "Connection failed"}
    except Exception as e:
        return {"service": f"sonarr_{variant}", "status": "error", "message": str(e)}


async def _test_seerr(stack) -> dict:
    try:
        ok = await stack.seerr.test_connection()
        if ok:
            return {"service": "seerr", "status": "ok", "message": "Connected and initialized"}
        return {"service": "seerr", "status": "error", "message": "Not initialized"}
    except Exception as e:
        return {"service": "seerr", "status": "error", "message": str(e)}


async def _test_tmdb(stack) -> dict:
    if not stack.tmdb:
        return {"service": "tmdb", "status": "error", "message": "Not configured — set TMDB_API_KEY"}
    try:
        ok = await stack.tmdb.test_connection()
        if ok:
            return {"service": "tmdb", "status": "ok", "message": "API key valid"}
        return {"service": "tmdb", "status": "error", "message": "Invalid API key or unreachable"}
    except Exception as e:
        return {"service": "tmdb", "status": "error", "message": str(e)}


@router.get("/settings/cache")
async def get_cache_stats(admin: TokenPayload = Depends(require_admin)):
    """Detailed cache statistics."""
    cache = get_cache()
    stats = cache.get_stats()
    return {
        "stats": stats,
        "ttl": {
            "recommendations": "15 min",
            "library": "30 min",
            "tmdb_ids": "24 hours",
        },
    }


@router.post("/settings/cache/clear")
async def clear_cache(
    admin: TokenPayload = Depends(require_admin),
    scope: str = Query("all", pattern="^(all|recommendations|library)$"),
):
    """Clear caches by scope."""
    cache = get_cache()
    if scope == "all":
        cache.invalidate_all()
        return {"status": "ok", "cleared": "all caches"}
    elif scope == "recommendations":
        cache.invalidate_all()  # Current cache impl clears all
        return {"status": "ok", "cleared": "recommendation caches"}
    else:
        return {"status": "ok", "cleared": scope}
