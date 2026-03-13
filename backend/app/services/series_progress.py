"""Series Progress — calculate TV series completion % per user.

Combines Tautulli episode watch history with Sonarr total episode counts
to produce per-series completion metrics for the frontend.

Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
"""

import logging
from typing import Optional

from app.services.factory import get_stack
from app.services.cache import get_cache

logger = logging.getLogger(__name__)


async def get_series_progress(
    username: str,
    tmdb_ids: list[int] | None = None,
) -> dict[int, dict]:
    """Get series completion data for a user.

    Args:
        username: Plex username
        tmdb_ids: Optional filter — only return progress for these TMDB IDs.
                  If None, returns all series the user has watched.

    Returns:
        {tmdb_id: {
            "title": str, "watched_episodes": int,
            "total_episodes": int|None, "completion_pct": float|None,
            "source": "sonarr"|"tautulli"
        }}
    """
    cache = get_cache()
    cache_key = f"series_progress:{username}"
    cached = cache.get_generic(cache_key)

    if cached is None:
        cached = await _build_series_progress(username)
        if cached:
            cache.set_generic(cache_key, cached, ttl=1800)  # 30 min cache

    if not cached:
        return {}

    # Filter to requested TMDB IDs if specified
    if tmdb_ids:
        filter_set = set(tmdb_ids)
        return {k: v for k, v in cached.items() if k in filter_set}

    return cached


async def _build_series_progress(username: str) -> dict[int, dict]:
    """Build full series progress map for a user."""
    stack = get_stack()
    result: dict[int, dict] = {}

    # Step 1: Get user's episode counts from Tautulli
    user_id = await _resolve_tautulli_user_id(stack, username)
    if not user_id:
        logger.warning(f"series_progress: could not resolve user_id for '{username}'")
        return {}

    try:
        episode_map = await stack.tautulli.get_episode_counts_by_series(user_id)
    except Exception as e:
        logger.error(f"series_progress: Tautulli episode fetch failed: {e}")
        return {}

    # Step 2: Build TMDB-keyed results from Tautulli data
    for _gp_key, info in episode_map.items():
        tmdb_id = info.get("tmdb_id")
        if not tmdb_id:
            continue
        result[tmdb_id] = {
            "title": info["title"],
            "watched_episodes": info["unique_episodes"],
            "total_episodes": None,
            "completion_pct": None,
            "source": "tautulli",
        }

    # Step 3: Enrich with Sonarr total episode counts
    sonarr_totals = await _get_sonarr_episode_totals(stack)
    for tmdb_id, entry in result.items():
        if tmdb_id in sonarr_totals:
            total = sonarr_totals[tmdb_id]["episode_count"]
            entry["total_episodes"] = total
            entry["source"] = "sonarr"
            if total and total > 0:
                entry["completion_pct"] = round(
                    min(entry["watched_episodes"] / total * 100, 100), 1
                )

    return result


async def _resolve_tautulli_user_id(stack, username: str) -> Optional[str]:
    """Resolve Plex username to Tautulli user_id."""
    try:
        users = await stack.tautulli.get_users()
        for u in users:
            if u.username and u.username.lower() == username.lower():
                return u.id
    except Exception as e:
        logger.warning(f"series_progress: user resolution failed: {e}")
    return None


async def _get_sonarr_episode_totals(stack) -> dict[int, dict]:
    """Get total episode counts from all Sonarr instances.

    Returns {tmdb_id: {"episode_count": N, "title": str}}.
    """
    cache = get_cache()
    cache_key = "sonarr_episode_totals"
    cached = cache.get_generic(cache_key)
    if cached:
        return cached

    totals: dict[int, dict] = {}

    for name in ("sonarr_tv", "sonarr_anime"):
        try:
            client = stack.registry.get(name)
            if not client or not hasattr(client, "get_all_series"):
                continue
            series_list = await client.get_all_series()
            for s in series_list:
                if s.tmdb_id and s.episode_count:
                    totals[s.tmdb_id] = {
                        "episode_count": s.episode_count,
                        "title": s.title,
                    }
        except Exception as e:
            logger.debug(f"series_progress: Sonarr {name} fetch: {e}")

    cache.set_generic(cache_key, totals, ttl=3600)  # 1hr cache
    return totals
