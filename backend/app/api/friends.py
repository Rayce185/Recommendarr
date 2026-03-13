"""Friend system API — request, accept, decline, remove, list."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.friends import (
    send_friend_request, respond_to_request, remove_friend,
    get_friends, get_pending_requests,
    get_privacy_settings, update_privacy_settings,
)

router = APIRouter()


class FriendRequestBody(BaseModel):
    username: str


class FriendResponseBody(BaseModel):
    username: str
    accept: bool


class PrivacyUpdateBody(BaseModel):
    show_activity_to_friends: bool | None = None
    anonymize_activity: bool | None = None
    contribute_to_collaborative: bool | None = None
    show_in_server_stats: bool | None = None
    allow_friend_requests: bool | None = None


@router.get("/friends")
async def list_friends(user: TokenPayload = Depends(get_current_user)):
    """Get current user's accepted friends."""
    return {"friends": get_friends(user.username)}


@router.get("/friends/pending")
async def list_pending(user: TokenPayload = Depends(get_current_user)):
    """Get incoming and outgoing pending friend requests."""
    return get_pending_requests(user.username)


@router.post("/friends/request")
async def request_friend(
    body: FriendRequestBody,
    user: TokenPayload = Depends(get_current_user),
):
    """Send a friend request to another user."""
    result = send_friend_request(user.username, body.username)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@router.post("/friends/respond")
async def respond_friend(
    body: FriendResponseBody,
    user: TokenPayload = Depends(get_current_user),
):
    """Accept or decline a friend request."""
    result = respond_to_request(user.username, body.username, body.accept)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@router.delete("/friends/{friend_username}")
async def delete_friend(
    friend_username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Remove a friend."""
    result = remove_friend(user.username, friend_username)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@router.get("/privacy")
async def get_my_privacy(user: TokenPayload = Depends(get_current_user)):
    """Get current user's privacy settings."""
    return get_privacy_settings(user.username)


@router.put("/privacy")
async def update_my_privacy(
    body: PrivacyUpdateBody,
    user: TokenPayload = Depends(get_current_user),
):
    """Update current user's privacy settings."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = update_privacy_settings(user.username, updates)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Failed"))
    return result


@router.get("/friends/activity")
async def get_friend_activity_feed(
    limit: int = 30,
    user: TokenPayload = Depends(get_current_user),
):
    """Get recent watch activity from the current user's friends."""
    from app.services.social import get_friend_activity
    from app.services.factory import get_stack
    from app.services.cache import get_cache

    cache = get_cache()
    cache_key = f"friend_activity:{user.username}"
    cached = cache.get_generic(cache_key)
    if cached is not None:
        return cached

    friend_list = get_friends(user.username)
    friend_usernames = [f["username"] for f in friend_list]

    if not friend_usernames:
        return {"activity": [], "friend_count": 0}

    stack = get_stack()
    activity = await get_friend_activity(stack.tautulli, friend_usernames, limit=limit)

    result = {"activity": activity, "friend_count": len(friend_usernames)}
    cache.set_generic(cache_key, result, ttl=300)  # 5 min cache
    return result
