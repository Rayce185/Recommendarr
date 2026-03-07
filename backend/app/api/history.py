"""Recommendation History API — browse past recommendations, manage exclusions.

GET  /users/{username}/rec-history          — paginated rec history
GET  /users/{username}/rec-history/stats    — aggregate stats
POST /users/{username}/rec-history/{tmdb_id}/interaction — mark clicked/watched/requested
"""

import logging

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.rec_history import get_history, get_history_stats, mark_interaction

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/users/{username}/rec-history")
async def get_user_history(
    username: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = Query(None, pattern="^(tonight|grab|rediscover|mood|group)$"),
    media_type: Optional[str] = Query(None, pattern="^(movie|tv)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Get paginated recommendation history for a user."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view another user's history")

    result = get_history(
        username=username,
        limit=limit,
        offset=offset,
        mode=mode,
        media_type=media_type,
    )
    return result


@router.get("/users/{username}/rec-history/stats")
async def get_user_history_stats(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Get aggregate recommendation history stats."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view another user's stats")

    return get_history_stats(username)


@router.post("/users/{username}/rec-history/{tmdb_id}/interaction")
async def record_interaction(
    username: str,
    tmdb_id: int,
    interaction: str = Query(..., pattern="^(clicked|watched|requested)$"),
    user: TokenPayload = Depends(get_current_user),
):
    """Mark a recommendation as clicked, watched, or requested."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot modify another user's history")

    success = mark_interaction(username, tmdb_id, interaction)
    if not success:
        raise HTTPException(404, "No history entry found for this item")

    return {"status": "ok", "tmdb_id": tmdb_id, "interaction": interaction}
