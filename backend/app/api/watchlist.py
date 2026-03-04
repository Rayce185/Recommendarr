"""Watchlist + Playback + User Preferences API."""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional

from app.services.factory import get_stack
from app.services.user_prefs import get_user_prefs
from app.auth.jwt_handler import TokenPayload, get_current_user

router = APIRouter()


# ── Watchlist ──────────────────────────────────────────────────

@router.get("/watchlist")
async def get_watchlist(
    sort: str = Query("addedAt:desc", pattern="^(addedAt|titleSort|year|rating):(asc|desc)$"),
    filter_type: Optional[str] = Query(None, alias="type", pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Get the authenticated user's Plex watchlist.

    Sort options: addedAt:desc, addedAt:asc, titleSort:asc, titleSort:desc,
                  year:desc, year:asc, rating:desc, rating:asc
    Filter: movie, tv, or omit for all.
    """
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")

    items = await stack.plex.get_watchlist(
        token_override=user.plex_token,
        sort=sort,
    )

    # Apply type filter
    if filter_type:
        items = [i for i in items if i["media_type"] == filter_type]

    # Enrich with library status + library name from Plex section map
    for item in items:
        if item["tmdb_id"]:
            label = "movie" if item["media_type"] == "movie" else "show"
            tmdb_key = f"{label}:{item['tmdb_id']}"
            item["in_library"] = bool(stack.plex._tmdb_map.get(tmdb_key))
            item["is_watched"] = stack.plex.is_watched(item["tmdb_id"], item["media_type"])
            item["plex_url"] = stack.plex.get_plex_url(item["tmdb_id"], item["media_type"])
            item["library_name"] = stack.plex._section_map.get(tmdb_key, None)

    # Build available libraries from Plex sections
    libraries = [{"key": s["key"], "title": s["title"], "type": s["type"]}
                 for s in stack.plex._sections]

    return {
        "items": items,
        "total": len(items),
        "sort": sort,
        "filter": filter_type,
        "libraries": libraries,
    }


@router.delete("/watchlist/{tmdb_id}")
async def remove_from_watchlist(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Remove an item from the user's Plex watchlist."""
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")

    plex_guid = await stack.plex.resolve_plex_guid(tmdb_id, media_type)
    if not plex_guid:
        raise HTTPException(404, f"Could not resolve TMDB {tmdb_id}")

    success = await stack.plex.remove_from_watchlist(plex_guid, token_override=user.plex_token)
    if not success:
        raise HTTPException(500, "Failed to remove from watchlist")

    return {"success": True, "tmdb_id": tmdb_id}


# ── Devices & Playback ───────────────────────────────────────

@router.get("/devices")
async def get_devices(
    user: TokenPayload = Depends(get_current_user),
):
    """Get available Plex player devices for the authenticated user."""
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")

    devices = await stack.plex.get_player_devices(token_override=user.plex_token)
    return {"devices": devices}


@router.post("/play/{tmdb_id}")
async def play_on_device(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    device_id: Optional[str] = Query(None, description="Target device clientIdentifier"),
    user: TokenPayload = Depends(get_current_user),
):
    """Start playback of a media item on a Plex player device.

    If no device_id specified, uses the user's default device from preferences.
    Item must be in the Plex library (has a ratingKey).
    """
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")

    # Resolve device
    target_device = device_id
    if not target_device:
        prefs = get_user_prefs()
        target_device = prefs.get(user.username, "default_device_id")
    if not target_device:
        raise HTTPException(400, "No device specified and no default device configured")

    # Resolve TMDB → ratingKey
    rating_key = stack.plex.get_plex_rating_key(tmdb_id, media_type)
    if not rating_key:
        raise HTTPException(404, f"TMDB {tmdb_id} not found in Plex library")

    result = await stack.plex.play_on_device(
        rating_key=rating_key,
        client_id=target_device,
        token_override=user.plex_token,
    )

    if not result["success"]:
        raise HTTPException(502, result["message"])

    return result


# ── User Preferences ──────────────────────────────────────────

@router.get("/preferences")
async def get_preferences(
    user: TokenPayload = Depends(get_current_user),
):
    """Get resolved preferences for the authenticated user.

    Each key includes value + source (user/global/default).
    """
    prefs = get_user_prefs()
    return {
        "preferences": prefs.get_all(user.username),
        "overrides": prefs.get_user_overrides(user.username),
    }


@router.put("/preferences")
async def update_preferences(
    updates: dict,
    user: TokenPayload = Depends(get_current_user),
):
    """Update per-user preferences. Only affects this user."""
    prefs = get_user_prefs()
    saved = prefs.set_user(user.username, updates)
    return {"saved": saved, "resolved": prefs.get_flat(user.username)}


@router.delete("/preferences/{key}")
async def reset_preference(
    key: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Reset a single preference to inherit from global/default."""
    prefs = get_user_prefs()
    removed = prefs.reset_user_key(user.username, key)
    return {"removed": removed, "key": key, "new_value": prefs.get(user.username, key)}


# ── Global Defaults (Admin Only) ─────────────────────────────

@router.get("/preferences/global")
async def get_global_preferences(
    user: TokenPayload = Depends(get_current_user),
):
    """Get global default preferences (admin only)."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    prefs = get_user_prefs()
    return {"global_defaults": prefs.get_global()}


@router.put("/preferences/global")
async def update_global_preferences(
    updates: dict,
    user: TokenPayload = Depends(get_current_user),
):
    """Update global default preferences (admin only).

    These apply to all users who haven't overridden the specific setting.
    """
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    prefs = get_user_prefs()
    saved = prefs.set_global(updates)
    return {"saved": saved}
