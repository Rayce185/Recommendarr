"""Plex client — library scanning, deep links, and delegated operations.

Core client handling Plex identity, library section scanning, TMDB map
building, and in-library lookups. Delegates watchlist and playback
operations to plex_watchlist and plex_playback modules.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import httpx

from app.clients import plex_watchlist, plex_playback

logger = logging.getLogger(__name__)


@dataclass
class PlexConfig:
    url: str
    token: str
    machine_id: str = ""


class PlexClient:
    """Lightweight Plex API client for recommendation deep links."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.machine_id: str = ""
        self._tmdb_map: dict[str, int] = {}
        self._section_map: dict[str, str] = {}
        self._watched_map: dict[str, int] = {}
        self._sections: list[dict] = []
        self._map_built_at: float = 0
        self._map_ttl: float = 1800

    async def init(self):
        """Fetch machine identifier (call once at startup)."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{self.url}/identity")
                r.raise_for_status()
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

    # ── Library Map Building ─────────────────────────────────────

    async def build_tmdb_map(self, force: bool = False, tvdb_to_tmdb: dict[int, int] | None = None):
        """Scan all library sections, extract tmdb GUIDs → ratingKey mapping."""
        if not force and self._tmdb_map and (time.time() - self._map_built_at) < self._map_ttl:
            return

        new_map: dict[str, int] = {}
        new_section_map: dict[str, str] = {}
        new_watched_map: dict[str, int] = {}
        tvdb_unresolved: list[tuple[int, int, str, str]] = []
        sections_raw = await self._get_sections()

        self._sections = []
        for sec_key, sec_type, sec_title in sections_raw:
            self._sections.append({"key": sec_key, "title": sec_title, "type": sec_type})
            try:
                items, watched, tvdb_only = await self._get_section_guids(sec_key, sec_type)
                new_map.update(items)
                new_watched_map.update(watched)
                for tmdb_key in items:
                    new_section_map[tmdb_key] = sec_title
                for tvdb_id, rating_key in tvdb_only.items():
                    tvdb_unresolved.append((tvdb_id, rating_key, sec_type, sec_title))
            except Exception as e:
                logger.warning(f"Failed to scan section {sec_key}: {e}")

        # Resolve tvdb-only items via Sonarr bridge
        bridge = tvdb_to_tmdb or {}
        resolved_count = 0
        for tvdb_id, rating_key, media_label, sec_title in tvdb_unresolved:
            tmdb_id = bridge.get(tvdb_id)
            if tmdb_id:
                key = f"{media_label}:{tmdb_id}"
                new_map[key] = rating_key
                new_section_map[key] = sec_title
                resolved_count += 1

        self._tmdb_map = new_map
        self._section_map = new_section_map
        self._watched_map = new_watched_map
        self._map_built_at = time.time()
        tvdb_total = len(tvdb_unresolved)
        if tvdb_total > 0:
            logger.info(f"Plex TMDB map built: {len(new_map)} items across {len(self._sections)} sections "
                        f"({resolved_count}/{tvdb_total} tvdb-only items resolved via Sonarr bridge)")
        else:
            logger.info(f"Plex TMDB map built: {len(new_map)} items across {len(self._sections)} sections")

    async def _get_sections(self) -> list[tuple[str, str, str]]:
        """Get library section keys, types, and titles."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.url}/library/sections",
                headers={"X-Plex-Token": self.token},
            )
            r.raise_for_status()
        root = ET.fromstring(r.text)
        return [
            (d.get("key"), stype, d.get("title", ""))
            for d in root.findall(".//Directory")
            if (stype := d.get("type", "")) in ("movie", "show")
        ]

    async def _get_section_guids(self, section_key: str, section_type: str) -> tuple[dict, dict, dict]:
        """Scan one library section for TMDB GUIDs, watched status, tvdb-only items."""
        plex_type = "1" if section_type == "movie" else "2"
        media_label = section_type

        mapping: dict[str, int] = {}
        watched: dict[str, int] = {}
        tvdb_only: dict[int, int] = {}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                f"{self.url}/library/sections/{section_key}/all",
                params={"type": plex_type, "includeGuids": "1", "X-Plex-Token": self.token},
            )
            r.raise_for_status()
        root = ET.fromstring(r.text)

        tag = "Video" if section_type == "movie" else "Directory"
        for item in root.findall(f".//{tag}"):
            rating_key = item.get("ratingKey")
            if not rating_key:
                continue
            view_count = int(item.get("viewCount", 0) or 0)
            found_tmdb = False
            tvdb_id_found = None
            for guid in item.findall(".//Guid"):
                gid = guid.get("id", "")
                m = re.match(r"tmdb://(\d+)", gid)
                if m:
                    tmdb_id = int(m.group(1))
                    key = f"{media_label}:{tmdb_id}"
                    mapping[key] = int(rating_key)
                    if view_count > 0:
                        watched[key] = view_count
                    found_tmdb = True
                    break
                m_tvdb = re.match(r"tvdb://(\d+)", gid)
                if m_tvdb:
                    tvdb_id_found = int(m_tvdb.group(1))
            if not found_tmdb and tvdb_id_found is not None:
                tvdb_only[tvdb_id_found] = int(rating_key)
        return mapping, watched, tvdb_only

    # ── Map Lookups ──────────────────────────────────────────────

    def get_plex_url(self, tmdb_id: int, media_type: str) -> Optional[str]:
        if not self.machine_id or not self._tmdb_map:
            return None
        label = "movie" if media_type == "movie" else "show"
        rk = self._tmdb_map.get(f"{label}:{tmdb_id}")
        if not rk:
            return None
        return f"https://app.plex.tv/desktop/#!/server/{self.machine_id}/details?key=%2Flibrary%2Fmetadata%2F{rk}"

    def get_plex_rating_key(self, tmdb_id: int, media_type: str) -> Optional[int]:
        label = "movie" if media_type == "movie" else "show"
        return self._tmdb_map.get(f"{label}:{tmdb_id}")

    def is_watched(self, tmdb_id: int, media_type: str) -> bool:
        label = "movie" if media_type == "movie" else "show"
        return f"{label}:{tmdb_id}" in self._watched_map

    def get_watched_count(self) -> int:
        return len(self._watched_map)

    def get_section_name(self, tmdb_id: int, media_type: str) -> Optional[str]:
        label = "movie" if media_type == "movie" else "show"
        return self._section_map.get(f"{label}:{tmdb_id}")

    def is_in_section(self, tmdb_id: int, media_type: str, section_names: set[str]) -> bool:
        section = self.get_section_name(tmdb_id, media_type)
        return section in section_names if section else False

    # ── Watchlist delegation ─────────────────────────────────────

    async def resolve_plex_guid(self, tmdb_id: int, media_type: str) -> Optional[str]:
        return await plex_watchlist.resolve_plex_guid(tmdb_id, media_type, self.token)

    async def add_to_watchlist(self, plex_rating_key: str, token_override: str = None) -> bool:
        return await plex_watchlist.add_to_watchlist(plex_rating_key, token_override or self.token)

    async def remove_from_watchlist(self, plex_rating_key: str, token_override: str = None) -> bool:
        return await plex_watchlist.remove_from_watchlist(plex_rating_key, token_override or self.token)

    async def get_watchlist(self, token_override: str = None, sort: str = "addedAt:desc") -> list[dict]:
        return await plex_watchlist.get_watchlist(
            token_override or self.token, self._tmdb_map, self._watched_map, sort,
        )

    # ── Playback delegation ──────────────────────────────────────

    async def get_player_devices(self, token_override: str = None) -> list[dict]:
        return await plex_playback.get_player_devices(token_override or self.token)

    async def play_on_device(self, rating_key: int, client_id: str, token_override: str = None) -> dict:
        return await plex_playback.play_on_device(
            rating_key, client_id, self.url, self.machine_id, token_override or self.token,
        )

    # ── Properties ───────────────────────────────────────────────

    @property
    def sections(self) -> list[dict]:
        return self._sections

    @property
    def map_size(self) -> int:
        return len(self._tmdb_map)
