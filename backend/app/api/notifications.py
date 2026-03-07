"""Notification Center — compute-on-read aggregation of what's relevant right now.

GET /notifications — returns categorized notifications for the current user.
No persistent event store: all notifications are computed from live data.
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.feedback import get_feedback_store
from app.services.factory import get_stack
from app.services.cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter()

FEEDBACK_MILESTONES = [10, 25, 50, 100, 250, 500]


def _calendar_notifications(stack, days=7) -> list[dict]:
    """Items releasing within the next N days (from Radarr/Sonarr)."""
    import asyncio
    notifications = []
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days)

    async def _fetch():
        items = []
        try:
            items.extend(await stack.radarr.get_calendar(days))
        except Exception:
            pass
        for name in ("sonarr_tv", "sonarr_anime"):
            try:
                client = stack.registry.get(name)
                if client and hasattr(client, "get_calendar"):
                    items.extend(await client.get_calendar(days))
            except Exception:
                pass
        return items

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context already — can't nest run
            import concurrent.futures
            # Just return empty; the async endpoint will call us properly
            return []
        items = asyncio.run(_fetch())
    except RuntimeError:
        return []

    for item in items:
        rd = item.get("release_date")
        if not rd:
            continue
        try:
            dt = datetime.strptime(rd.split("T")[0], "%Y-%m-%d")
            if now <= dt <= cutoff:
                days_until = (dt - now).days
                notifications.append({
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

    notifications.sort(key=lambda x: x.get("release_date", "9999"))
    return notifications


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

    all_notifs = calendar_items + milestones + system
    priority_order = {"high": 0, "normal": 1, "low": 2}
    all_notifs.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 9))

    result = {
        "notifications": all_notifs,
        "counts": {
            "total": len(all_notifs),
            "calendar": len(calendar_items),
            "milestones": len(milestones),
            "system": len(system),
            "high_priority": sum(1 for n in all_notifs if n.get("priority") == "high"),
        },
    }
    cache.set_generic(cache_key, result, ttl=cache.NOTIFICATIONS_TTL)
    return result
