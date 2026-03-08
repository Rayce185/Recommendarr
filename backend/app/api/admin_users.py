"""Admin User Management — staleness monitoring and per-user cache warming.

GET  /admin/users/staleness    — per-user freshness with plays-since-refresh
POST /admin/users/{username}/warm — trigger full cache warm for one user
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.cache import get_cache
from app.services.factory import get_stack, resolve_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users/staleness")
async def get_user_staleness(user: TokenPayload = Depends(get_current_user)):
    """Per-user staleness: plays since last refresh, cache ages, warm status."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")

    stack = get_stack()
    cache = get_cache()

    # Get all users from Tautulli
    users = await stack.tautulli.get_users()
    refreshes = cache.get_all_user_refreshes()

    results = []
    for u in users:
        uname = u.get("username", "")
        if not uname:
            continue

        last_refresh_epoch = refreshes.get(uname)
        plays_since = 0
        total_plays = 0

        # Count plays since last refresh via Tautulli
        total_plays = int(u.get("plays", 0) or 0)
        uid = u.get("user_id")
        if uid and last_refresh_epoch:
            try:
                since_dt = datetime.fromtimestamp(
                    last_refresh_epoch, tz=timezone.utc,
                )
                history = await stack.tautulli.get_history(
                    user_id=str(uid), since=since_dt, limit=200,
                )
                plays_since = len(history)
            except Exception as e:
                logger.debug(f"Staleness check for {uname}: {e}")

        # Determine staleness level
        if last_refresh_epoch is None:
            staleness = "never"
        elif plays_since == 0:
            staleness = "fresh"
        elif plays_since < 5:
            staleness = "slightly_stale"
        elif plays_since < 20:
            staleness = "stale"
        else:
            staleness = "very_stale"

        refresh_age_hours = (
            round((time.time() - last_refresh_epoch) / 3600, 1)
            if last_refresh_epoch else None
        )

        results.append({
            "username": uname,
            "friendly_name": u.get("friendly_name", uname),
            "thumb": u.get("thumb", ""),
            "is_active": bool(u.get("is_active", 0)),
            "plays_since_refresh": plays_since,
            "total_plays": total_plays,
            "staleness": staleness,
            "last_refresh_at": (
                datetime.fromtimestamp(last_refresh_epoch, tz=timezone.utc).isoformat()
                if last_refresh_epoch else None
            ),
            "refresh_age_hours": refresh_age_hours,
        })

    # Sort: active first, then by staleness severity
    staleness_order = {"never": 0, "very_stale": 1, "stale": 2, "slightly_stale": 3, "fresh": 4}
    results.sort(key=lambda r: (
        0 if r["is_active"] else 1,
        staleness_order.get(r["staleness"], 5),
        -r["plays_since_refresh"],
    ))

    return {"users": results, "total": len(results)}


@router.post("/users/{username}/warm")
async def warm_user(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Trigger full cache warm for a specific user.

    Builds taste profile, generates recommendations for all modes,
    and scans collections. Returns timing summary.
    """
    if not user.is_admin:
        raise HTTPException(403, "Admin only")

    stack = get_stack()
    cache = get_cache()
    timings = {}
    errors = []

    # 1. Build taste profile
    t0 = time.time()
    try:
        profile = await asyncio.wait_for(
            stack.profiler.build_profile(username, domain="all"),
            timeout=15.0,
        )
        timings["profile"] = round((time.time() - t0) * 1000)
        logger.info(f"Warm {username}: profile built ({timings['profile']}ms)")
    except Exception as e:
        timings["profile"] = -1
        errors.append(f"Profile: {e}")

    # 2. Generate recommendations for each mode
    from app.services.recommender import RecommendationRequest
    for mode in ("tonight", "grab", "rediscover"):
        t0 = time.time()
        try:
            req = RecommendationRequest(
                username=username, mode=mode, domain="all", limit=30,
            )
            recs = await asyncio.wait_for(
                stack.engine.recommend(req), timeout=30.0,
            )
            timings[f"recs_{mode}"] = round((time.time() - t0) * 1000)
            logger.info(f"Warm {username}: {mode} ({len(recs)} recs, {timings[f'recs_{mode}']}ms)")
        except Exception as e:
            timings[f"recs_{mode}"] = -1
            errors.append(f"{mode}: {e}")

    # 3. Collections scan
    t0 = time.time()
    try:
        from app.services.collections import CollectionService
        if not hasattr(stack, "_collection_svc") or stack._collection_svc is None:
            stack._collection_svc = CollectionService(
                stack.tmdb, stack.radarr, stack.tautulli,
            )
        collections = await asyncio.wait_for(
            stack._collection_svc.get_user_collections(username),
            timeout=60.0,
        )
        timings["collections"] = round((time.time() - t0) * 1000)
        logger.info(f"Warm {username}: collections ({len(collections)} found, {timings['collections']}ms)")
    except Exception as e:
        timings["collections"] = -1
        errors.append(f"Collections: {e}")

    # Record refresh timestamp
    cache.set_user_refresh(username)
    total_ms = sum(v for v in timings.values() if v > 0)

    return {
        "username": username,
        "status": "ok" if not errors else "partial",
        "timings": timings,
        "total_ms": total_ms,
        "errors": errors if errors else None,
    }
