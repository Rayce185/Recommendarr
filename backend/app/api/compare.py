"""Taste comparison API — multi-user profile overlay for radar charts.

GET /compare?users=user1,user2,user3&domain=all
Returns normalized genre vectors for radar chart rendering, plus
comparison statistics (shared genres, divergence, similarity).
"""

import asyncio
import logging
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.factory import get_stack
from app.services.cache import get_cache
from app.services.social import compute_genre_overlap

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_COMPARE_USERS = 6
COMPARE_CACHE_TTL = 600  # 10 minutes


@router.get("/compare")
async def compare_profiles(
    users: str = Query(..., description="Comma-separated usernames (2-6)"),
    domain: str = Query("all", pattern="^(all|movies|tv|anime)$"),
    current_user: TokenPayload = Depends(get_current_user),
):
    """Compare taste profiles of multiple users for radar chart overlay.

    Returns genre axes (union of all users' top genres) with normalized
    scores per user, plus pairwise similarity and shared/unique genres.
    """
    usernames = [u.strip() for u in users.split(",") if u.strip()]
    if len(usernames) < 2:
        raise HTTPException(400, "Need at least 2 usernames to compare")
    if len(usernames) > MAX_COMPARE_USERS:
        raise HTTPException(400, f"Max {MAX_COMPARE_USERS} users for comparison")

    # Deduplicate while preserving order
    seen = set()
    unique_users = []
    for u in usernames:
        if u not in seen:
            seen.add(u)
            unique_users.append(u)
    usernames = unique_users

    cache = get_cache()
    cache_key = f"compare:{','.join(sorted(usernames))}:{domain}"
    cached = cache.get_generic(cache_key)
    if cached is not None:
        return cached

    stack = get_stack()

    # Build profiles in parallel
    async def _build(username: str):
        try:
            p = cache.get_profile(username, domain)
            if p is None:
                p = await asyncio.wait_for(
                    stack.profiler.build_profile(
                        username=username, domain=domain,
                        enrich_keywords=True, max_enrich=80,
                    ),
                    timeout=20.0,
                )
                cache.set_profile(username, domain, p)
            return username, p
        except Exception as e:
            logger.warning(f"Failed to build profile for {username}: {e}")
            return username, None

    results = await asyncio.gather(*[_build(u) for u in usernames])
    profiles = {name: p for name, p in results if p is not None}

    if len(profiles) < 2:
        raise HTTPException(
            422,
            f"Could only build {len(profiles)} profile(s). Need at least 2.",
        )

    # Build unified genre axes — union of each user's top N genres
    genre_union = set()
    for p in profiles.values():
        for g in p.top_genres(10):
            genre_union.add(g.genre)

    # Sort axes alphabetically for consistent radar layout
    axes = sorted(genre_union)

    # Build radar data per user
    radar_users = []
    for username in usernames:
        if username not in profiles:
            continue
        p = profiles[username]
        scores = [p.genre_score(g) for g in axes]
        radar_users.append({
            "username": username,
            "scores": scores,
            "stats": {
                "total_watched": p.total_watched,
                "total_hours": round(p.total_hours, 1),
                "avg_completion": round(p.avg_completion, 1),
                "rewatch_count": p.rewatch_count,
            },
            "top_keywords": [
                {"keyword": k.keyword, "score": k.score}
                for k in p.top_keywords(10)
            ],
        })

    # Pairwise similarity matrix
    pairs = []
    user_list = [u["username"] for u in radar_users]
    for i, u1 in enumerate(user_list):
        for u2 in user_list[i + 1:]:
            pct, shared, unique = compute_genre_overlap(
                profiles[u1], profiles[u2],
            )
            pairs.append({
                "user_a": u1,
                "user_b": u2,
                "similarity_pct": pct,
                "shared_genres": shared,
                "unique_to_b": unique,
            })

    result = {
        "axes": axes,
        "users": radar_users,
        "pairs": pairs,
        "domain": domain,
    }
    cache.set_generic(cache_key, result, ttl=COMPARE_CACHE_TTL)
    return result
