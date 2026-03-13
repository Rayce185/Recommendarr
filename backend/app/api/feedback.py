"""Feedback API — thumbs up/down/dismiss on recommendations.

POST /users/{username}/feedback   — Submit feedback
GET  /users/{username}/feedback   — Get all feedback for user
DELETE /users/{username}/feedback/{tmdb_id} — Remove feedback
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.feedback import get_feedback_store, FeedbackEntry
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    tmdb_id: int
    media_type: str = "movie"
    action: str  # "up", "down", "dismiss"
    title: str = ""
    genres: list[str] = []
    keywords: list[str] = []
    reason: str = ""


@router.post("/users/{username}/feedback")
async def submit_feedback(
    username: str,
    body: FeedbackRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Submit thumbs up/down/dismiss on a recommendation."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot submit feedback for another user")

    if body.action not in ("up", "down", "dismiss"):
        raise HTTPException(400, "action must be 'up', 'down', or 'dismiss'")

    store = get_feedback_store()
    entry = FeedbackEntry(
        tmdb_id=body.tmdb_id,
        media_type=body.media_type,
        action=body.action,
        title=body.title,
        genres=body.genres,
        keywords=body.keywords,
        reason=body.reason,
    )
    store.add(username, entry)

    # Invalidate cached recs so feedback takes effect on next load
    get_cache().invalidate_user(username)

    # ChromaDB sync (non-blocking)
    from app.services.chroma_sync import get_chroma_sync, fire_and_forget
    sync = get_chroma_sync()
    if sync:
        fire_and_forget(sync.sync_feedback(
            username, body.tmdb_id, body.media_type, body.title, body.action))

    return {"status": "ok", "action": body.action, "tmdb_id": body.tmdb_id}


@router.get("/users/{username}/feedback")
async def get_feedback(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Get all feedback entries for a user."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot view another user's feedback")

    store = get_feedback_store()
    entries = store.get_all(username)
    return {
        "feedback": [e.to_dict() for e in entries],
        "stats": store.get_stats(username),
    }


@router.delete("/users/{username}/feedback/{tmdb_id}")
async def delete_feedback(
    username: str,
    tmdb_id: int,
    user: TokenPayload = Depends(get_current_user),
):
    """Remove feedback for a specific item."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot modify another user's feedback")

    store = get_feedback_store()
    store.remove(username, tmdb_id)
    return {"status": "ok", "tmdb_id": tmdb_id}
