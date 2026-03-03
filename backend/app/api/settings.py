"""System Settings API — admin configuration, service testing, cache management."""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.services.factory import get_stack
from app.services.cache import get_cache
from app.config import settings
from app.services.settings_store import get_settings_store, EDITABLE_FIELDS
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
async def get_settings(
    admin: TokenPayload = Depends(require_admin),
    edit: bool = Query(False, description="Return unmasked values for editing"),
):
    """Get current system configuration.

    With edit=false (default): keys are masked for display.
    With edit=true: returns full values for the settings editor.
    """
    store = get_settings_store()
    overrides = store.get_all_overrides()

    def _val(field: str, display_val: str = None) -> str:
        """Return the current effective value for a field."""
        return getattr(settings, field, display_val or "")

    def _key_display(field: str) -> str:
        """Return masked or full key depending on edit mode."""
        val = _val(field)
        if edit:
            return val
        return _mask_key(val)

    def _is_overridden(field: str) -> bool:
        return field in overrides

    result = {
        "services": {
            "plex": {
                "url": {"value": _val("plex_url"), "field": "plex_url", "overridden": _is_overridden("plex_url")},
                "api_key": {"value": _key_display("plex_token"), "field": "plex_token", "overridden": _is_overridden("plex_token")},
                "machine_id": {"value": _val("plex_machine_id"), "field": "plex_machine_id", "overridden": _is_overridden("plex_machine_id")},
            },
            "tautulli": {
                "url": {"value": _val("tautulli_url"), "field": "tautulli_url", "overridden": _is_overridden("tautulli_url")},
                "api_key": {"value": _key_display("tautulli_api_key"), "field": "tautulli_api_key", "overridden": _is_overridden("tautulli_api_key")},
            },
            "radarr": {
                "url": {"value": _val("radarr_url"), "field": "radarr_url", "overridden": _is_overridden("radarr_url")},
                "api_key": {"value": _key_display("radarr_api_key"), "field": "radarr_api_key", "overridden": _is_overridden("radarr_api_key")},
            },
            "sonarr_tv": {
                "url": {"value": _val("sonarr_url"), "field": "sonarr_url", "overridden": _is_overridden("sonarr_url")},
                "api_key": {"value": _key_display("sonarr_api_key"), "field": "sonarr_api_key", "overridden": _is_overridden("sonarr_api_key")},
            },
            "sonarr_anime": {
                "url": {"value": _val("sonarr_anime_url"), "field": "sonarr_anime_url", "overridden": _is_overridden("sonarr_anime_url")},
                "api_key": {"value": _key_display("sonarr_anime_api_key"), "field": "sonarr_anime_api_key", "overridden": _is_overridden("sonarr_anime_api_key")},
            },
            "seerr": {
                "url": {"value": _val("seerr_url"), "field": "seerr_url", "overridden": _is_overridden("seerr_url")},
                "api_key": {"value": _key_display("seerr_api_key"), "field": "seerr_api_key", "overridden": _is_overridden("seerr_api_key")},
            },
            "tmdb": {
                "url": {"value": "https://api.themoviedb.org/3", "field": None, "overridden": False},
                "api_key": {"value": _key_display("tmdb_api_key"), "field": "tmdb_api_key", "overridden": _is_overridden("tmdb_api_key")},
            },
        },

        "auth": {
            "jwt_expiry_hours": {"value": settings.jwt_expiry_hours, "field": "jwt_expiry_hours", "overridden": _is_overridden("jwt_expiry_hours")},
        },
        "app": {
            "debug": {"value": settings.debug, "field": "debug", "overridden": _is_overridden("debug")},
            "log_level": {"value": settings.log_level, "field": "log_level", "overridden": _is_overridden("log_level")},
        },
    }
    return result


class SettingsUpdate(BaseModel):
    """Payload for updating settings. Only include fields to change."""
    settings: Dict[str, Any]


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    admin: TokenPayload = Depends(require_admin),
):
    """Update system settings. Persists to JSON overlay.

    Body: {"settings": {"plex_url": "http://...", "tautulli_api_key": "abc..."}}
    Only editable fields are accepted. Unknown/protected fields are silently ignored.
    """
    store = get_settings_store()

    # Filter to editable fields only
    valid_updates = {k: v for k, v in body.settings.items() if k in EDITABLE_FIELDS}
    if not valid_updates:
        raise HTTPException(400, "No valid editable fields in request")

    # Save to persistent store
    saved = store.update(valid_updates)

    # Apply to running config
    settings.apply_overrides(saved)

    return {
        "status": "ok",
        "updated": list(saved.keys()),
        "message": f"Updated {len(saved)} setting(s). Changes are live immediately.",
        "note": "Service clients may need restart to pick up new URLs/keys. Use the Services tab to test connections.",
    }


@router.delete("/settings/{field}")
async def revert_setting(
    field: str,
    admin: TokenPayload = Depends(require_admin),
):
    """Revert a single setting to its env var / default value."""
    if field not in EDITABLE_FIELDS:
        raise HTTPException(400, f"Field '{field}' is not editable")

    store = get_settings_store()
    removed = store.remove(field)
    if not removed:
        return {"status": "ok", "message": f"'{field}' was not overridden"}

    # Reload the original env value — re-create settings to get original
    # For now, we can't easily revert a single field without re-reading env,
    # so we note it requires container restart for full revert
    return {
        "status": "ok",
        "message": f"Override for '{field}' removed. Container restart needed to revert to env value.",
    }


@router.post("/settings/test-connection")
async def test_connection(
    admin: TokenPayload = Depends(require_admin),
    service: str = Query(..., description="Service name to test"),
):
    """Test connectivity to a specific backend service."""
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
        return {"service": service, "status": "error", "message": str(e)}


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
        return {"service": "tautulli", "status": "ok", "message": f"{len(users)} users loaded", "details": {"users": len(users)}}
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
        "ttl": {"recommendations": "15 min", "library": "30 min", "tmdb_ids": "24 hours"},
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
        cache.invalidate_all()
        return {"status": "ok", "cleared": "recommendation caches"}
    else:
        return {"status": "ok", "cleared": scope}
