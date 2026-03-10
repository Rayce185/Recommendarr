"""Push Notification API — subscribe, unsubscribe, send test.

Manages Web Push subscriptions and provides the VAPID public key
for frontend service worker registration.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.models.core import User
from app.database import get_db
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])


# ── Request Models ───────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class SendTestRequest(BaseModel):
    title: str = "Test Notification"
    body: str = "Push notifications are working!"


# ── Public (no auth needed) ──────────────────────────────────────

@router.get("/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for frontend subscription."""
    from app.services.push_service import get_vapid_public_key
    return {"public_key": get_vapid_public_key()}


# ── Authenticated ────────────────────────────────────────────────

@router.post("/subscribe")
async def subscribe_push(
    body: SubscribeRequest,
    request: Request,
    user: TokenPayload = Depends(get_current_user),
):
    """Register a push subscription for the authenticated user."""
    from app.services.push_service import subscribe

    db = get_db()
    try:
        user_row = db.execute(
            select(User).where(User.plex_user_id == user.plex_user_id)
        ).scalar_one_or_none()
        if not user_row:
            raise HTTPException(404, "User not found")

        ua = request.headers.get("User-Agent", "")[:500]
        sub = subscribe(user_row.id, body.endpoint, body.p256dh, body.auth, ua)
        return {"subscribed": True, "id": sub.id}
    finally:
        db.close()


@router.post("/unsubscribe")
async def unsubscribe_push(
    body: SubscribeRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Remove a push subscription."""
    from app.services.push_service import unsubscribe

    db = get_db()
    try:
        user_row = db.execute(
            select(User).where(User.plex_user_id == user.plex_user_id)
        ).scalar_one_or_none()
        if not user_row:
            raise HTTPException(404, "User not found")

        removed = unsubscribe(user_row.id, body.endpoint)
        return {"unsubscribed": removed}
    finally:
        db.close()


@router.get("/status")
async def push_status(user: TokenPayload = Depends(get_current_user)):
    """Check how many push subscriptions the current user has."""
    from app.services.push_service import get_user_subscriptions

    db = get_db()
    try:
        user_row = db.execute(
            select(User).where(User.plex_user_id == user.plex_user_id)
        ).scalar_one_or_none()
        if not user_row:
            return {"subscriptions": 0}

        subs = get_user_subscriptions(user_row.id)
        return {
            "subscriptions": len(subs),
            "devices": [
                {"id": s.id, "user_agent": s.user_agent, "created_at": str(s.created_at)}
                for s in subs
            ],
        }
    finally:
        db.close()


@router.post("/test")
async def send_test_push(
    body: SendTestRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Send a test push notification to the current user."""
    from app.services.push_service import send_push

    db = get_db()
    try:
        user_row = db.execute(
            select(User).where(User.plex_user_id == user.plex_user_id)
        ).scalar_one_or_none()
        if not user_row:
            raise HTTPException(404, "User not found")

        result = send_push(
            user_row.id, body.title, body.body,
            tag="test", url="/settings",
        )
        if result.get("no_subscriptions"):
            raise HTTPException(400, "No push subscriptions found. Enable notifications first.")
        return result
    finally:
        db.close()
