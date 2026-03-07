"""Plex watchlist operations — add, remove, list, resolve GUIDs.

Standalone async functions that take explicit connection params.
PlexClient delegates to these for backward compatibility.
"""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PLEX_DISCOVER_BASE = "https://discover.provider.plex.tv"


async def resolve_plex_guid(
    tmdb_id: int,
    media_type: str,
    token: str,
) -> Optional[str]:
    """Resolve TMDB ID to Plex metadata GUID (for watchlist operations)."""
    import xml.etree.ElementTree as ET

    plex_type = "1" if media_type == "movie" else "2"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{PLEX_DISCOVER_BASE}/library/metadata/matches",
                params={
                    "type": plex_type,
                    "guid": f"tmdb://{tmdb_id}",
                    "X-Plex-Token": token,
                },
            )
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                for item in root:
                    rk = item.get("ratingKey", "")
                    if rk:
                        return rk
    except Exception as e:
        logger.warning(f"Plex GUID resolution failed for tmdb:{tmdb_id}: {e}")
    return None


async def add_to_watchlist(
    plex_rating_key: str,
    token: str,
) -> bool:
    """Add an item to a user's Plex watchlist."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(
                f"{PLEX_DISCOVER_BASE}/actions/addToWatchlist",
                params={"ratingKey": plex_rating_key, "X-Plex-Token": token},
            )
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"Plex watchlist add failed: {e}")
        return False


async def remove_from_watchlist(
    plex_rating_key: str,
    token: str,
) -> bool:
    """Remove an item from a user's Plex watchlist."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(
                f"{PLEX_DISCOVER_BASE}/actions/removeFromWatchlist",
                params={"ratingKey": plex_rating_key, "X-Plex-Token": token},
            )
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"Plex watchlist remove failed: {e}")
        return False


async def get_watchlist(
    token: str,
    tmdb_map: dict[str, int],
    watched_map: dict[str, int],
    sort: str = "addedAt:desc",
) -> list[dict]:
    """Fetch a user's Plex watchlist with TMDB IDs.

    Args:
        token: Plex user token
        tmdb_map: "movie:12345" → ratingKey mapping (for in_library check)
        watched_map: "movie:12345" → viewCount mapping (for is_watched check)
        sort: Sort field:direction (addedAt:desc, titleSort:asc, etc.)
    """
    items = []
    try:
        all_metadata = []
        offset = 0
        page_size = 20
        async with httpx.AsyncClient(timeout=30) as c:
            while True:
                r = await c.get(
                    f"{PLEX_DISCOVER_BASE}/library/sections/watchlist/all",
                    params={
                        "X-Plex-Token": token,
                        "includeGuids": "1",
                        "sort": sort,
                    },
                    headers={
                        "Accept": "application/json",
                        "X-Plex-Client-Identifier": "recommendarr",
                        "X-Plex-Container-Start": str(offset),
                        "X-Plex-Container-Size": str(page_size),
                    },
                )
                r.raise_for_status()
                data = r.json()
                mc = data.get("MediaContainer", {})
                page_items = mc.get("Metadata", [])
                all_metadata.extend(page_items)
                total = mc.get("totalSize", len(page_items))
                offset += len(page_items)
                if offset >= total or not page_items:
                    break

        for item in all_metadata:
            tmdb_id = None
            for g in item.get("Guid", []):
                gid = g.get("id", "")
                if gid.startswith("tmdb://"):
                    tmdb_id = int(gid.replace("tmdb://", ""))
                    break
            media_type = "movie" if item.get("type") == "movie" else "tv"
            label = "movie" if media_type == "movie" else "show"
            in_library = bool(tmdb_map.get(f"{label}:{tmdb_id}")) if tmdb_id else False
            is_watched = f"{label}:{tmdb_id}" in watched_map if tmdb_id else False

            items.append({
                "tmdb_id": tmdb_id,
                "plex_rating_key": item.get("ratingKey"),
                "title": item.get("title", ""),
                "year": item.get("year"),
                "media_type": media_type,
                "poster_url": item.get("thumb"),
                "added_at": item.get("addedAt"),
                "vote_average": item.get("rating") or 0,
                "genres": [g.get("tag", "") for g in item.get("Genre", [])],
                "overview": item.get("summary", ""),
                "in_library": in_library,
                "is_watched": is_watched,
            })
    except Exception as e:
        logger.error(f"Watchlist fetch failed: {e}")
    return items
