"""Minimal Plex client for deep-link resolution.

Scans Plex library sections and builds tmdb_id → ratingKey mapping.
Used to generate "Play in Plex" URLs for in-library recommendations.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PlexConfig:
    url: str            # e.g. http://192.168.0.111:32400
    token: str
    machine_id: str = ""


class PlexClient:
    """Lightweight Plex API client for recommendation deep links."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.machine_id: str = ""
        self._tmdb_map: dict[str, int] = {}   # "movie:12345" → ratingKey
        self._section_map: dict[str, str] = {}  # "movie:12345" → section name
        self._watched_map: dict[str, int] = {}   # "movie:12345" → viewCount
        self._sections: list[dict] = []          # [{key, title, type}]
        self._map_built_at: float = 0
        self._map_ttl: float = 1800  # 30 min

    async def init(self):
        """Fetch machine identifier (call once at startup)."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{self.url}/identity")
                r.raise_for_status()
                # Parse XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.text)
                self.machine_id = root.get("machineIdentifier", "")
                logger.info(f"Plex connected: machineId={self.machine_id[:12]}...")
        except Exception as e:
            logger.error(f"Plex identity failed: {e}")

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{self.url}/identity",
                    headers={"X-Plex-Token": self.token},
                )
                return r.status_code == 200
        except Exception:
            return False

    async def build_tmdb_map(self, force: bool = False):
        """Scan all library sections, extract tmdb GUIDs → ratingKey mapping."""
        if not force and self._tmdb_map and (time.time() - self._map_built_at) < self._map_ttl:
            return  # Cache still fresh

        new_map: dict[str, int] = {}
        new_section_map: dict[str, str] = {}
        new_watched_map: dict[str, int] = {}
        sections_raw = await self._get_sections()

        self._sections = []
        for sec_key, sec_type, sec_title in sections_raw:
            self._sections.append({"key": sec_key, "title": sec_title, "type": sec_type})
            try:
                items, watched = await self._get_section_guids(sec_key, sec_type)
                new_map.update(items)
                new_watched_map.update(watched)
                # Tag each item with its section name
                for tmdb_key in items:
                    new_section_map[tmdb_key] = sec_title
            except Exception as e:
                logger.warning(f"Failed to scan section {sec_key}: {e}")

        self._tmdb_map = new_map
        self._section_map = new_section_map
        self._watched_map = new_watched_map
        self._map_built_at = time.time()
        logger.info(f"Plex TMDB map built: {len(new_map)} items across {len(self._sections)} sections")

    async def _get_sections(self) -> list[tuple[str, str, str]]:
        """Get library section keys, types, and titles."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.url}/library/sections",
                headers={"X-Plex-Token": self.token},
            )
            r.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        result = []
        for d in root.findall(".//Directory"):
            stype = d.get("type", "")
            if stype in ("movie", "show"):
                result.append((d.get("key"), stype, d.get("title", "")))
        return result

    async def _get_section_guids(self, section_key: str, section_type: str) -> tuple[dict[str, int], dict[str, int]]:
        """Scan one library section for TMDB GUIDs and watched status."""
        plex_type = "1" if section_type == "movie" else "2"
        media_label = section_type  # "movie" or "show"

        mapping: dict[str, int] = {}
        watched: dict[str, int] = {}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                f"{self.url}/library/sections/{section_key}/all",
                params={
                    "type": plex_type,
                    "includeGuids": "1",
                    "X-Plex-Token": self.token,
                },
            )
            r.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)

        tag = "Video" if section_type == "movie" else "Directory"
        for item in root.findall(f".//{tag}"):
            rating_key = item.get("ratingKey")
            if not rating_key:
                continue
            view_count = int(item.get("viewCount", 0) or 0)
            for guid in item.findall(".//Guid"):
                gid = guid.get("id", "")
                m = re.match(r"tmdb://(\d+)", gid)
                if m:
                    tmdb_id = int(m.group(1))
                    key = f"{media_label}:{tmdb_id}"
                    mapping[key] = int(rating_key)
                    if view_count > 0:
                        watched[key] = view_count
                    break

        return mapping, watched

    def get_plex_url(self, tmdb_id: int, media_type: str) -> Optional[str]:
        """Get Plex web deep link for a TMDB ID. Returns None if not in library."""
        if not self.machine_id or not self._tmdb_map:
            return None

        # Normalize media_type
        label = "movie" if media_type == "movie" else "show"
        key = f"{label}:{tmdb_id}"
        rating_key = self._tmdb_map.get(key)

        if not rating_key:
            return None

        return (
            f"https://app.plex.tv/desktop/#!/server/{self.machine_id}"
            f"/details?key=%2Flibrary%2Fmetadata%2F{rating_key}"
        )

    def get_plex_rating_key(self, tmdb_id: int, media_type: str) -> Optional[int]:
        """Get Plex rating key for a TMDB ID."""
        label = "movie" if media_type == "movie" else "show"
        return self._tmdb_map.get(f"{label}:{tmdb_id}")

    def is_watched(self, tmdb_id: int, media_type: str) -> bool:
        """Check if an item has been watched (viewCount > 0 in Plex)."""
        label = "movie" if media_type == "movie" else "show"
        return f"{label}:{tmdb_id}" in self._watched_map

    def get_watched_count(self) -> int:
        """Return count of watched items."""
        return len(self._watched_map)

    def get_section_name(self, tmdb_id: int, media_type: str) -> Optional[str]:
        """Get the Plex library section name for a TMDB ID."""
        label = "movie" if media_type == "movie" else "show"
        return self._section_map.get(f"{label}:{tmdb_id}")

    def is_in_section(self, tmdb_id: int, media_type: str, section_names: set[str]) -> bool:
        """Check if an item belongs to any of the given section names."""
        section = self.get_section_name(tmdb_id, media_type)
        return section in section_names if section else False

    # ── Watchlist ──────────────────────────────────────────────────

    async def resolve_plex_guid(self, tmdb_id: int, media_type: str) -> Optional[str]:
        """Resolve TMDB ID to Plex metadata GUID (for watchlist operations).

        Uses Plex discover API: guid=tmdb://ID maps directly to Plex ratingKey.
        """
        import xml.etree.ElementTree as ET
        plex_type = "1" if media_type == "movie" else "2"
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    "https://discover.provider.plex.tv/library/metadata/matches",
                    params={
                        "type": plex_type,
                        "guid": f"tmdb://{tmdb_id}",
                        "X-Plex-Token": self.token,
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

    async def add_to_watchlist(self, plex_rating_key: str, token_override: str = None) -> bool:
        """Add an item to a user's Plex watchlist.
        
        Args:
            token_override: If provided, use this user's token instead of admin token.
                           Enables per-user watchlist operations.
        """
        token = token_override or self.token
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.put(
                    f"https://discover.provider.plex.tv/actions/addToWatchlist",
                    params={
                        "ratingKey": plex_rating_key,
                        "X-Plex-Token": token,
                    },
                )
                return r.status_code == 200
        except Exception as e:
            logger.warning(f"Plex watchlist add failed: {e}")
            return False

    async def remove_from_watchlist(self, plex_rating_key: str, token_override: str = None) -> bool:
        """Remove an item from a user's Plex watchlist.
        
        Args:
            token_override: If provided, use this user's token instead of admin token.
        """
        token = token_override or self.token
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.put(
                    f"https://discover.provider.plex.tv/actions/removeFromWatchlist",
                    params={
                        "ratingKey": plex_rating_key,
                        "X-Plex-Token": token,
                    },
                )
                return r.status_code == 200
        except Exception as e:
            logger.warning(f"Plex watchlist remove failed: {e}")
            return False

    @property
    def sections(self) -> list[dict]:
        """Return list of library sections."""
        return self._sections

    @property
    def map_size(self) -> int:
        return len(self._tmdb_map)
