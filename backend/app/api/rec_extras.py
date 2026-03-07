"""Extra discovery routes — World Cinema Map and Reddit Buzz.

Niche discovery features that extend beyond standard TMDB trending.
"""

from fastapi import APIRouter, Query
from typing import Optional

from app.services.factory import get_stack
from app.services.cache import get_cache

router = APIRouter()


@router.get("/discover/world-cinema")
async def get_world_cinema_map(
    username: Optional[str] = Query(None, description="Username for taste matching"),
):
    """World cinema map with per-country taste match scores."""
    from app.services.world_cinema import get_world_cinema_map as _get_map

    user_genres = None
    if username:
        try:
            stack = get_stack()
            cache = get_cache()
            profile = cache.get_profile(username, "all")
            if not profile:
                profile = await stack.profiler.build_profile(
                    username=username, domain="all", enrich_keywords=False,
                )
                cache.set_profile(username, "all", profile)
            user_genres = {g.genre: g.score for g in profile.genres}
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"World cinema taste profile failed: {e}")

    return _get_map(user_genres)


@router.get("/discover/buzz")
async def get_reddit_buzz_endpoint(
    subreddits: Optional[str] = Query(None, description="Comma-separated subreddit names"),
    limit: int = Query(15, ge=5, le=30, description="Posts per subreddit"),
    enrich: bool = Query(True, description="Cross-reference with TMDB"),
):
    """Talk of the Web — Reddit-powered film/TV buzz."""
    from app.services.reddit_buzz import get_reddit_buzz, SOURCES

    stack = get_stack()
    sub_list = subreddits.split(",") if subreddits else None
    items = await get_reddit_buzz(
        seerr_client=stack.seerr, subreddits=sub_list,
        limit_per_sub=limit, enrich_tmdb=enrich,
    )
    available_subs = [{"name": s["sub"], "label": s["label"], "category": s["category"]} for s in SOURCES]
    return {"results": items, "total": len(items), "sources": available_subs}
