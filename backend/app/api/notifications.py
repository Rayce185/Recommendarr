"""Notification Center — compute-on-read aggregation of what's relevant right now.

GET /notifications — returns categorized notifications for the current user.
No persistent event store: all notifications are computed from live data.
"""

import json
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.feedback import get_feedback_store
from app.services.factory import get_stack
from app.database import get_db
from app.models import GroupNightSession
from app.services.cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter()

FEEDBACK_MILESTONES = [10, 25, 50, 100, 250, 500]


def _feedback_notifications(username: str) -> list[dict]:
    """Milestone notifications based on feedback count."""
    store = get_feedback_store()
    stats = store.get_stats(username)
    total = stats["total"]
    notifications = []

    for milestone in FEEDBACK_MILESTONES:
        if total >= milestone:
            notifications.append({
                "type": "milestone",
                "priority": "low",
                "title": f"{milestone} Ratings!",
                "message": f"You've rated {total} titles — your taste profile keeps getting smarter.",
                "icon": "star",
            })
            break  # Only show the highest milestone reached

    return notifications


def _service_notifications(stack) -> list[dict]:
    """Surface any service health issues."""
    notifications = []
    # Check if any service is unhealthy
    services_to_check = [
        ("tautulli", "Tautulli"),
        ("radarr", "Radarr"),
    ]
    for attr, label in services_to_check:
        try:
            client = getattr(stack, attr, None)
            if client is None:
                notifications.append({
                    "type": "system",
                    "priority": "high",
                    "title": f"{label} Unavailable",
                    "message": f"{label} is not configured or unreachable.",
                    "icon": "alert",
                })
        except Exception:
            pass

    return notifications



def _group_night_notifications(username: str, days=7) -> list[dict]:
    """Recent group night sessions where user is invited."""
    try:
        from sqlalchemy import select
        cutoff = datetime.utcnow() - timedelta(days=days)
        with get_db() as db:
            rows = db.execute(select(GroupNightSession).where(
                GroupNightSession.created_at >= cutoff, GroupNightSession.creator != username,
                GroupNightSession.participants.contains(f'"{username}"')
            )).scalars().all()
        return [{"type": "group_night", "priority": "normal",
            "title": r.title or f"Group Night from {r.creator}",
            "message": f"{r.creator} shared {len(json.loads(r.picks))} picks with you",
            "icon": "users", "link": f"#group/{r.code}", "code": r.code,
        } for r in rows]
    except Exception as e:
        logger.debug("Group night notifications error: %s", e)
        return []


def _friend_request_notifications(username: str) -> list[dict]:
    """Pending incoming friend requests."""
    try:
        from app.services.friends import get_pending_requests
        pending = get_pending_requests(username)
        return [
            {
                "type": "friend_request",
                "priority": "normal",
                "title": f"Friend Request",
                "message": f"{r['display_name']} wants to be your friend",
                "icon": "user-plus",
                "username": r["username"],
                "thumb": r.get("thumb", ""),
            }
            for r in pending.get("incoming", [])
        ]
    except Exception as e:
        logger.debug("Friend request notifications error: %s", e)
        return []


@router.get("/notifications")
async def get_notifications(
    user: TokenPayload = Depends(get_current_user),
):
    """Compute and return all active notifications for the current user."""
    cache = get_cache()
    cache_key = f"notif:{user.username}"
    cached = cache.get_generic(cache_key)
    if cached:
        return cached

    stack = get_stack()
    username = user.username

    # ── Calendar (async-safe) ────────────────────────────────
    calendar_items = []
    now = datetime.utcnow()
    cutoff = now + timedelta(days=7)
    try:
        arr_items = []
        try:
            arr_items.extend(await stack.radarr.get_calendar(7))
        except Exception:
            pass
        for name in ("sonarr_tv", "sonarr_anime"):
            try:
                client = stack.registry.get(name)
                if client and hasattr(client, "get_calendar"):
                    arr_items.extend(await client.get_calendar(7))
            except Exception:
                pass

        for item in arr_items:
            rd = item.get("release_date")
            if not rd:
                continue
            try:
                dt = datetime.strptime(rd.split("T")[0], "%Y-%m-%d")
                if now.date() <= dt.date() <= cutoff.date():
                    days_until = (dt.date() - now.date()).days
                    calendar_items.append({
                        "type": "calendar",
                        "priority": "high" if days_until <= 1 else "normal",
                        "title": item.get("title", "Unknown"),
                        "message": "Releases today!" if days_until == 0 else f"Releasing in {days_until} day{'s' if days_until != 1 else ''}",
                        "tmdb_id": item.get("tmdb_id"),
                        "media_type": item.get("media_type", "movie"),
                        "release_date": rd.split("T")[0],
                        "icon": "calendar",
                    })
            except (ValueError, TypeError):
                continue
        calendar_items.sort(key=lambda x: x.get("release_date", "9999"))
    except Exception as e:
        logger.debug("Calendar notifications error: %s", e)

    # ── Feedback milestones ──────────────────────────────────
    milestones = _feedback_notifications(username)

    # ── System health ────────────────────────────────────────
    system = _service_notifications(stack)

    # ── Friend requests ──────────────────────────────────
    friend_reqs = _friend_request_notifications(username)

    # ── Group Night invites ────────────────────────────────
    group_nights = _group_night_notifications(username)

    all_notifs = calendar_items + milestones + system + friend_reqs + group_nights

    # Add stable IDs and filter dismissed
    for n in all_notifs:
        n["id"] = _notif_id(n)
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    dismissed = set(store.get(f"dismissed_notifs:{user.username}") or [])
    all_notifs = [n for n in all_notifs if n["id"] not in dismissed]

    priority_order = {"high": 0, "normal": 1, "low": 2}
    all_notifs.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 9))

    result = {
        "notifications": all_notifs,
        "counts": {
            "total": len(all_notifs),
            "calendar": len(calendar_items),
            "milestones": len(milestones),
            "system": len(system),
            "friend_requests": len(friend_reqs),
            "group_nights": len(group_nights),
            "high_priority": sum(1 for n in all_notifs if n.get("priority") == "high"),
        },
    }
    cache.set_generic(cache_key, result, ttl=cache.NOTIFICATIONS_TTL)
    return result


@router.post("/notifications/dismiss")
async def dismiss_notification(
    body: dict,
    user: TokenPayload = Depends(get_current_user),
):
    """Dismiss a notification so it won't show again."""
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    key = f"dismissed_notifs:{user.username}"
    dismissed = store.get(key) or []
    notif_id = body.get("id")
    if notif_id and notif_id not in dismissed:
        dismissed.append(notif_id)
        store.set(key, dismissed)
    # Invalidate notification cache
    cache = get_cache()
    cache.delete_generic(f"notif:{user.username}")
    return {"dismissed": len(dismissed)}


@router.post("/notifications/dismiss-all")
async def dismiss_all_notifications(
    user: TokenPayload = Depends(get_current_user),
):
    """Dismiss all current notifications."""
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    key = f"dismissed_notifs:{user.username}"
    # Get current notifications to know what to dismiss
    result = await get_notifications(user)
    ids = [_notif_id(n) for n in result.get("notifications", [])]
    store.set(key, ids)
    cache = get_cache()
    cache.delete_generic(f"notif:{user.username}")
    return {"dismissed": len(ids)}


@router.delete("/notifications/dismissed")
async def clear_dismissed(
    user: TokenPayload = Depends(get_current_user),
):
    """Clear dismissed list (show all notifications again)."""
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    store.set(f"dismissed_notifs:{user.username}", [])
    cache = get_cache()
    cache.delete_generic(f"notif:{user.username}")
    return {"cleared": True}


def _notif_id(notif: dict) -> str:
    """Generate a stable ID for a notification."""
    parts = [notif.get("type", ""), notif.get("title", "")]
    if notif.get("tmdb_id"):
        parts.append(str(notif["tmdb_id"]))
    if notif.get("release_date"):
        parts.append(notif["release_date"])
    return ":".join(parts)
