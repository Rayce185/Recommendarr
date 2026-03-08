"""Social layer API — taste overlap and server-wide stats."""

from fastapi import APIRouter, Query, HTTPException
from app.services.factory import get_stack
from app.services.social import get_taste_overlaps, get_server_stats
from app.services.cache import get_cache

router = APIRouter()

SOCIAL_CACHE_TTL = 1800  # 30 minutes
STATS_CACHE_TTL = 3600   # 1 hour


@router.get("/users/{username}/taste-overlap")
async def get_user_taste_overlaps(
    username: str,
    domain: str = Query("all", pattern="^(all|movies|tv|anime)$"),
):
    """Get taste overlap scores between this user and all other active users."""
    cache = get_cache()
    cache_key = f"social:overlap:{username}:{domain}"
    cached = cache.get_generic(cache_key)
    if cached is not None:
        return cached

    stack = get_stack()

    try:
        overlaps = await get_taste_overlaps(
            profiler=stack.profiler,
            tautulli=stack.tautulli,
            username=username,
            domain=domain,
        )
        result = {
            "username": username,
            "domain": domain,
            "overlaps": [
                {
                    "username": o.username,
                    "friendly_name": o.friendly_name,
                    "thumb": o.thumb,
                    "overlap_pct": o.overlap_pct,
                    "shared_genres": o.shared_genres,
                    "unique_to_them": o.unique_to_them,
                }
                for o in overlaps
            ],
            "count": len(overlaps),
        }
        cache.set_generic(cache_key, result, ttl=SOCIAL_CACHE_TTL)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to compute overlaps: {e}")


@router.get("/social/server-stats")
async def get_server_overview():
    """Get server-wide viewing stats and trending titles."""
    cache = get_cache()
    cache_key = "social:server_stats"
    cached = cache.get_generic(cache_key)
    if cached is not None:
        return cached

    stack = get_stack()
    try:
        result = await get_server_stats(stack.tautulli)
        cache.set_generic(cache_key, result, ttl=STATS_CACHE_TTL)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to get server stats: {e}")
