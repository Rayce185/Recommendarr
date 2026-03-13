"""Media request & watchlist API routes.

Seerr request proxy and Plex watchlist management.
"""

from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends

from app.services.factory import get_stack
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.config import settings

router = APIRouter()


# ── Seerr Request ────────────────────────────────────────────────

@router.post("/request/{tmdb_id}")
async def request_media(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    seasons: Optional[str] = None,
):
    """Submit a media request through Seerr → Radarr/Sonarr."""
    stack = get_stack()
    try:
        if media_type == "movie":
            result = await stack.seerr.request_movie(tmdb_id)
        else:
            season_list = None
            if seasons:
                season_list = [int(s.strip()) for s in seasons.split(",")]
            result = await stack.seerr.request_tv(tmdb_id, season_list)
    except Exception as e:
        raise HTTPException(400, f"Request failed: {e}")

    return {
        "request_id": result.request_id,
        "tmdb_id": result.tmdb_id,
        "media_type": result.media_type,
        "status": result.status,
        "requested_by": result.requested_by,
    }


# ── Plex Watchlist ───────────────────────────────────────────────

@router.post("/watchlist/add/{tmdb_id}")
async def add_to_watchlist(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Add a title to the authenticated user's Plex watchlist."""
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")

    plex_guid = await stack.plex.resolve_plex_guid(tmdb_id, media_type)
    if not plex_guid:
        raise HTTPException(404, f"Could not resolve TMDB {tmdb_id} to Plex metadata")

    success = await stack.plex.add_to_watchlist(plex_guid, token_override=user.plex_token)
    if not success:
        raise HTTPException(500, "Failed to add to Plex watchlist")

    return {"success": True, "tmdb_id": tmdb_id, "plex_guid": plex_guid, "user": user.username}


@router.post("/watchlist/remove/{tmdb_id}")
async def remove_from_watchlist(
    tmdb_id: int,
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Remove a title from the authenticated user's Plex watchlist."""
    stack = get_stack()
    if not stack.plex:
        raise HTTPException(503, "Plex not configured")

    plex_guid = await stack.plex.resolve_plex_guid(tmdb_id, media_type)
    if not plex_guid:
        raise HTTPException(404, f"Could not resolve TMDB {tmdb_id} to Plex metadata")

    success = await stack.plex.remove_from_watchlist(plex_guid, token_override=user.plex_token)
    if not success:
        raise HTTPException(500, "Failed to remove from Plex watchlist")

    return {"success": True, "tmdb_id": tmdb_id, "user": user.username}
