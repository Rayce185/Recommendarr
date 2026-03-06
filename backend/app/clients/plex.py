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

    async def build_tmdb_map(self, force: bool = False, tvdb_to_tmdb: dict[int, int] | None = None):
        """Scan all library sections, extract tmdb GUIDs → ratingKey mapping.

        Args:
            force: Rebuild even if cache is fresh.
            tvdb_to_tmdb: Optional {tvdb_id: tmdb_id} bridge from Sonarr.
                          Used to resolve anime items that only have tvdb:// GUIDs in Plex.
        """
        if not force and self._tmdb_map and (time.time() - self._map_built_at) < self._map_ttl:
            return  # Cache still fresh

        new_map: dict[str, int] = {}
        new_section_map: dict[str, str] = {}
        new_watched_map: dict[str, int] = {}
        tvdb_unresolved: list[tuple[int, int, str, str]] = []  # (tvdb_id, rating_key, media_label, section_title)
        sections_raw = await self._get_sections()

        self._sections = []
        for sec_key, sec_type, sec_title in sections_raw:
            self._sections.append({"key": sec_key, "title": sec_title, "type": sec_type})
            try:
                items, watched, tvdb_only = await self._get_section_guids(sec_key, sec_type)
                new_map.update(items)
                new_watched_map.update(watched)
                # Tag each item with its section name
                for tmdb_key in items:
                    new_section_map[tmdb_key] = sec_title
                # Collect tvdb-only items for bridge resolution
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

        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        result = []
        for d in root.findall(".//Directory"):
            stype = d.get("type", "")
            if stype in ("movie", "show"):
                result.append((d.get("key"), stype, d.get("title", "")))
        return result

    async def _get_section_guids(self, section_key: str, section_type: str) -> tuple[dict[str, int], dict[str, int], dict[int, int]]:
        """Scan one library section for TMDB GUIDs, watched status, and tvdb-only items.

        Returns (tmdb_mapping, watched_mapping, tvdb_only_mapping).
        tvdb_only_mapping: {tvdb_id: rating_key} for items that lack a tmdb:// GUID.
        """
        plex_type = "1" if section_type == "movie" else "2"
        media_label = section_type  # "movie" or "show"

        mapping: dict[str, int] = {}
        watched: dict[str, int] = {}
        tvdb_only: dict[int, int] = {}  # tvdb_id → ratingKey (no tmdb GUID)
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
            # Items with only tvdb GUID — need Sonarr bridge to resolve tmdb ID
            if not found_tmdb and tvdb_id_found is not None:
                tvdb_only[tvdb_id_found] = int(rating_key)

        return mapping, watched, tvdb_only

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

    # ── Watchlist Listing ────────────────────────────────────────────

    async def get_watchlist(self, token_override: str = None, sort: str = "addedAt:desc") -> list[dict]:
        """Fetch a user's Plex watchlist with TMDB IDs.

        Args:
            token_override: User's Plex token (defaults to admin token)
            sort: Sort field:direction (addedAt:desc, titleSort:asc, year:desc, rating:desc)

        Returns list of dicts with tmdb_id, title, year, type, poster, addedAt, etc.
        """
        token = token_override or self.token
        items = []
        try:
            # Plex discover API hard-limits at 20 per page — paginate
            all_metadata = []
            offset = 0
            page_size = 20
            async with httpx.AsyncClient(timeout=30) as c:
                while True:
                    r = await c.get(
                        "https://discover.provider.plex.tv/library/sections/watchlist/all",
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
                    # Extract TMDB ID from Guid array
                    tmdb_id = None
                    for g in item.get("Guid", []):
                        gid = g.get("id", "")
                        if gid.startswith("tmdb://"):
                            tmdb_id = int(gid.replace("tmdb://", ""))
                            break
                    media_type = "movie" if item.get("type") == "movie" else "tv"
                    poster = item.get("thumb") or None
                    # Check in-library status
                    in_library = bool(self._tmdb_map.get(f"{'movie' if media_type == 'movie' else 'show'}:{tmdb_id}")) if tmdb_id else False
                    is_watched_val = self.is_watched(tmdb_id, media_type) if tmdb_id else False

                    items.append({
                        "tmdb_id": tmdb_id,
                        "plex_rating_key": item.get("ratingKey"),
                        "title": item.get("title", ""),
                        "year": item.get("year"),
                        "media_type": media_type,
                        "poster_url": poster,
                        "added_at": item.get("addedAt"),
                        "vote_average": (item.get("rating") or 0),
                        "genres": [g.get("tag", "") for g in item.get("Genre", [])],
                        "overview": item.get("summary", ""),
                        "in_library": in_library,
                        "is_watched": is_watched_val,
                    })
        except Exception as e:
            logger.error(f"Watchlist fetch failed: {e}")
        return items

    # ── Device / Resource Enumeration ──────────────────────────────

    async def get_player_devices(self, token_override: str = None) -> list[dict]:
        """Get available Plex player devices (clients that can play media).

        Returns list of player devices with name, product, clientId, connections.
        """
        token = token_override or self.token
        devices = []
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    "https://plex.tv/api/v2/resources",
                    params={
                        "X-Plex-Token": token,
                        "includeHttps": 1,
                        "includeRelay": 1,
                    },
                    headers={
                        "Accept": "application/json",
                        "X-Plex-Client-Identifier": "recommendarr",
                    },
                )
                r.raise_for_status()
                data = r.json()
                for res in data:
                    provides = res.get("provides", "")
                    if "player" not in provides:
                        continue
                    # Find best connection (prefer local)
                    conns = res.get("connections", [])
                    local_conn = next((c for c in conns if c.get("local")), None)
                    best_conn = local_conn or (conns[0] if conns else None)
                    devices.append({
                        "client_id": res.get("clientIdentifier", ""),
                        "name": res.get("name", "Unknown"),
                        "product": res.get("product", ""),
                        "platform": res.get("platform", ""),
                        "provides": provides,
                        "connection_uri": best_conn.get("uri") if best_conn else None,
                        "owned": res.get("owned", False),
                        "last_seen": res.get("lastSeenAt"),
                    })
        except Exception as e:
            logger.error(f"Plex resources fetch failed: {e}")
        return devices

    # ── Playback Control ─────────────────────────────────────────

    async def play_on_device(
        self,
        rating_key: int,
        client_id: str,
        token_override: str = None,
    ) -> dict:
        """Initiate playback of a media item on a specific Plex player.

        Uses Plex playQueues + commandManager to start playback on the target device.
        The server acts as controller, sending the play command to the client.

        Args:
            rating_key: Plex library ratingKey of the item
            client_id: Target player's clientIdentifier
            token_override: User's Plex token for auth

        Returns: {"success": bool, "message": str}
        """
        token = token_override or self.token
        headers = {
            "X-Plex-Token": token,
            "X-Plex-Client-Identifier": "recommendarr",
            "X-Plex-Target-Client-Identifier": client_id,
        }

        try:
            # Step 1: Create a play queue on the server
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    f"{self.url}/playQueues",
                    params={
                        "type": "video",
                        "uri": f"server://{self.machine_id}/com.plexapp.plugins.library/library/metadata/{rating_key}",
                        "shuffle": 0,
                        "repeat": 0,
                        "continuous": 0,
                        "own": 1,
                        "X-Plex-Token": token,
                        "X-Plex-Client-Identifier": "recommendarr",
                    },
                    headers={"Accept": "application/json"},
                )
                if r.status_code not in (200, 201):
                    return {"success": False, "message": f"Failed to create play queue: HTTP {r.status_code}"}
                pq = r.json()
                pq_id = pq.get("MediaContainer", {}).get("playQueueID")
                if not pq_id:
                    return {"success": False, "message": "No playQueueID returned"}

            # Step 2: Send playMedia command to the target device via server
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{self.url}/player/playback/playMedia",
                    params={
                        "key": f"/library/metadata/{rating_key}",
                        "machineIdentifier": self.machine_id,
                        "address": self.url.split("://")[1].split(":")[0],
                        "port": self.url.split(":")[-1],
                        "protocol": "http",
                        "containerKey": f"/playQueues/{pq_id}?own=1&window=200",
                        "commandID": 1,
                        "type": "video",
                        "X-Plex-Token": token,
                        "X-Plex-Target-Client-Identifier": client_id,
                    },
                    headers={
                        "X-Plex-Client-Identifier": "recommendarr",
                        "X-Plex-Target-Client-Identifier": client_id,
                    },
                )
                if r.status_code == 200:
                    return {"success": True, "message": f"Playback started (queue {pq_id})"}
                else:
                    return {"success": False, "message": f"Player command failed: HTTP {r.status_code} - {r.text[:200]}"}

        except httpx.ConnectError:
            return {"success": False, "message": "Cannot reach device — it may be offline"}
        except Exception as e:
            return {"success": False, "message": str(e)[:200]}

    @property
    def sections(self) -> list[dict]:
        """Return list of library sections."""
        return self._sections

    @property
    def map_size(self) -> int:
        return len(self._tmdb_map)
