"""Social layer API — taste overlap and server-wide stats."""

from fastapi import APIRouter, Query, HTTPException
from app.services.factory import get_stack
from app.services.social import get_taste_overlaps, get_server_stats

router = APIRouter()


@router.get("/users/{username}/taste-overlap")
async def get_user_taste_overlaps(
    username: str,
    domain: str = Query("all", pattern="^(all|movies|tv|anime)$"),
):
    """Get taste overlap scores between this user and all other active users."""
    stack = get_stack()

    try:
        overlaps = await get_taste_overlaps(
            profiler=stack.profiler,
            tautulli=stack.tautulli,
            username=username,
            domain=domain,
        )
        return {
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
    except Exception as e:
        raise HTTPException(500, f"Failed to compute overlaps: {e}")


@router.get("/social/server-stats")
async def get_server_overview():
    """Get server-wide viewing stats and trending titles."""
    stack = get_stack()
    try:
        return await get_server_stats(stack.tautulli)
    except Exception as e:
        raise HTTPException(500, f"Failed to get server stats: {e}")
