"""Plex Wrapped — viewing statistics API endpoint."""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.services.factory import get_stack
from app.services.wrapped import build_wrapped

router = APIRouter()


@router.get("/users/{username}/wrapped")
async def get_user_wrapped(
    username: str,
    year: Optional[int] = Query(None, description="Year to analyze (default: current year)"),
):
    """Get Plex Wrapped viewing statistics for a user."""
    stack = get_stack()

    users = await stack.tautulli.get_users()
    user_match = None
    for u in users:
        if u.get("username", "").lower() == username.lower():
            user_match = u
            break
        if u.get("friendly_name", "").lower() == username.lower():
            user_match = u
            break

    if not user_match:
        raise HTTPException(404, f"User '{username}' not found")

    user_id = str(user_match.get("user_id"))

    try:
        result = await build_wrapped(
            tautulli=stack.tautulli,
            user_id=user_id,
            username=username,
            year=year,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to build wrapped: {e}")
