"""Plex Media Server client — IMediaServer implementation.

Handles: library scanning, user sync with sharing permissions,
media info extraction, playback control, playlist/collection creation.
"""

import httpx
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree

from app.clients.base import (
    IMediaServer, MediaLibrary, MediaItem, ServerUser, PlaybackClient,
)


class PlexClient(IMediaServer):
    """Plex Media Server implementation of IMediaServer."""

    def __init__(self, url: str, token: str, machine_id: Optional[str] = None):
        self.url = url.rstrip("/")
        self.token = token
        self.machine_id = machine_id
        self._headers = {
            "X-Plex-Token": token,
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Make authenticated GET request to Plex."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.url}{path}",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _get_xml(self, url: str) -> ElementTree.Element:
        """Make authenticated GET request expecting XML (for plex.tv APIs)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"X-Plex-Token": self.token},
            )
            resp.raise_for_status()
            return ElementTree.fromstring(resp.text)

    # ── IMediaServer implementation ──────────────────────────────

    async def get_libraries(self) -> list[MediaLibrary]:
        """List all Plex libraries with accurate item counts."""
        data = await self._get("/library/sections")
        libs = []
        for d in data["MediaContainer"].get("Directory", []):
            lib_id = d["key"]
            # Fetch accurate count via container size trick
            count = await self._get_library_count(lib_id)
            libs.append(MediaLibrary(
                id=lib_id,
                name=d["title"],
                type=d["type"],  # "movie" | "show"
                item_count=count,
            ))
        return libs

    async def _get_library_count(self, library_id: str) -> int:
        """Get accurate item count for a library without fetching all items."""
        try:
            data = await self._get(
                f"/library/sections/{library_id}/all",
                {"X-Plex-Container-Start": "0", "X-Plex-Container-Size": "0"},
            )
            return data["MediaContainer"].get("totalSize", 0)
        except Exception:
            return 0

    async def get_library_items(self, library_id: str) -> list[MediaItem]:
        """Get all items in a library with TMDB/IMDB GUIDs."""
        data = await self._get(f"/library/sections/{library_id}/all", {"includeGuids": "1"})
        items = []
        for m in data["MediaContainer"].get("Metadata", []):
            item = self._parse_item(m, library_id)
            items.append(item)
        return items

    async def get_item(self, item_key: str) -> Optional[MediaItem]:
        """Get a single item by rating key."""
        try:
            data = await self._get(f"/library/metadata/{item_key}")
            metadata = data["MediaContainer"].get("Metadata", [])
            if metadata:
                return self._parse_item(metadata[0])
        except Exception:
            return None
        return None

    async def get_users(self) -> list[ServerUser]:
        """Get all server users with library sharing permissions.

        Combines local /accounts with plex.tv sharing API for permission data.
        """
        # Step 1: Get local accounts
        data = await self._get("/accounts")
        accounts = data["MediaContainer"].get("Account", [])

        # Step 2: Get sharing permissions from plex.tv
        sharing_map: dict[str, list[str]] = {}  # username → [accessible section keys]
        if self.machine_id:
            try:
                root = await self._get_xml(
                    f"https://plex.tv/api/servers/{self.machine_id}/shared_servers"
                )
                for ss in root.findall(".//SharedServer"):
                    username = ss.get("username", "")
                    accessible = []
                    for section in ss.findall(".//Section"):
                        if section.get("shared") == "1":
                            accessible.append(section.get("key", ""))
                    sharing_map[username.lower()] = accessible
            except Exception:
                pass  # Sharing API optional — degrade gracefully

        users = []
        for acc in accounts:
            acc_id = str(acc.get("id", ""))
            name = acc.get("name", "")

            # Server owner has access to everything
            is_admin = acc_id in ("0", "1") or not name
            accessible = sharing_map.get(name.lower(), [])

            users.append(ServerUser(
                id=acc_id,
                username=name,
                display_name=name,
                thumb_url=acc.get("thumb"),
                is_admin=is_admin,
                accessible_library_ids=accessible if not is_admin else [],
            ))
        return users

    async def get_user_ratings(self, user_id: str) -> list[tuple[str, float]]:
        """Get user ratings. Plex stores these per-library."""
        # TODO: iterate libraries, query rated items
        return []

    async def get_clients(self) -> list[PlaybackClient]:
        """Get active Plex clients/players."""
        data = await self._get("/clients")
        clients = []
        for c in data["MediaContainer"].get("Server", []):
            clients.append(PlaybackClient(
                id=c.get("machineIdentifier", ""),
                name=c.get("name", "Unknown"),
                platform=c.get("platform"),
                state="idle",
                controllable=True,
            ))

        # Also check active sessions for playing state
        try:
            sessions = await self._get("/status/sessions")
            for s in sessions["MediaContainer"].get("Metadata", []):
                player = s.get("Player", {})
                machine_id = player.get("machineIdentifier", "")
                for client in clients:
                    if client.id == machine_id:
                        client.state = player.get("state", "playing")
                        client.current_item_key = s.get("ratingKey")
                        break
        except Exception:
            pass

        return clients

    async def play_on_device(self, device_id: str, item_key: str, resume: bool = False) -> bool:
        """Start playback on a Plex client."""
        params = {
            "key": f"/library/metadata/{item_key}",
            "machineIdentifier": device_id,
        }
        if resume:
            params["viewOffset"] = 0  # Plex handles resume from server state

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/player/playback/playMedia",
                    headers=self._headers,
                    params=params,
                )
                return resp.status_code < 400
        except Exception:
            return False

    async def create_playlist(self, user_id: str, title: str, item_keys: list[str]) -> Optional[str]:
        """Create a Plex playlist for a user."""
        if not item_keys:
            return None

        uri_items = ",".join(
            f"server://{self.machine_id}/com.plexapp.plugins.library/library/metadata/{k}"
            for k in item_keys
        )
        params = {
            "type": "video",
            "title": title,
            "smart": "0",
            "uri": uri_items,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.url}/playlists",
                    headers=self._headers,
                    params=params,
                )
                if resp.status_code < 400:
                    data = resp.json()
                    return data["MediaContainer"]["Metadata"][0].get("ratingKey")
        except Exception:
            pass
        return None

    async def create_collection(self, library_id: str, title: str, item_keys: list[str]) -> Optional[str]:
        """Create a collection in a Plex library."""
        if not item_keys:
            return None

        # Plex collections are created by adding items to a named collection
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for key in item_keys:
                    await client.put(
                        f"{self.url}/library/sections/{library_id}/all",
                        headers=self._headers,
                        params={
                            "type": 1,  # movie
                            "id": key,
                            "collection[0].tag.tag": title,
                        },
                    )
            return title  # Plex collections don't have a key
        except Exception:
            return None

    async def get_media_info(self, item_key: str) -> Optional[MediaItem]:
        """Get detailed media info (codecs, resolution, HDR, audio)."""
        try:
            data = await self._get(f"/library/metadata/{item_key}")
            metadata = data["MediaContainer"].get("Metadata", [])
            if not metadata:
                return None

            m = metadata[0]
            item = self._parse_item(m)

            # Extract quality details from Media/Part/Stream
            media_list = m.get("Media", [])
            if media_list:
                media = media_list[0]  # Primary media version
                item.video_codec = media.get("videoCodec")
                item.video_resolution = media.get("videoResolution")
                item.audio_codec = media.get("audioCodec")

                # HDR detection
                streams = media.get("Part", [{}])[0].get("Stream", [])
                for stream in streams:
                    if stream.get("streamType") == 1:  # video stream
                        dovi = stream.get("DOVIPresent")
                        hdr = stream.get("colorTrc")
                        if dovi:
                            item.hdr_type = "Dolby Vision"
                        elif hdr in ("smpte2084", "arib-std-b67"):
                            item.hdr_type = "HDR10"
            return item
        except Exception:
            return None

    async def test_connection(self) -> bool:
        """Test Plex server reachability."""
        try:
            data = await self._get("/identity")
            return "MediaContainer" in data
        except Exception:
            return False

    # ── Plex-specific methods ────────────────────────────────────

    async def get_all_library_guids(self, library_id: str) -> dict[str, str]:
        """Get TMDB/IMDB GUIDs for all items in a library.

        Returns: {plex_rating_key: tmdb_id}
        Used for cross-referencing Plex items with TMDB metadata.
        Requires includeGuids=1 to get external IDs in list view.
        """
        data = await self._get(f"/library/sections/{library_id}/all", {"includeGuids": "1"})
        guid_map = {}
        for m in data["MediaContainer"].get("Metadata", []):
            key = m.get("ratingKey", "")
            guids = m.get("Guid", [])
            # Two-pass: prefer TMDB, fall back to IMDB
            tmdb_found = False
            for g in guids:
                guid_id = g.get("id", "")
                if guid_id.startswith("tmdb://"):
                    guid_map[key] = guid_id.replace("tmdb://", "")
                    tmdb_found = True
                    break
            if not tmdb_found:
                for g in guids:
                    guid_id = g.get("id", "")
                    if guid_id.startswith("imdb://"):
                        guid_map[key] = guid_id  # Keep imdb:// prefix for later resolution
                        break
        return guid_map

    # ── Internal helpers ─────────────────────────────────────────

    def _parse_item(self, m: dict, library_id: str | None = None) -> MediaItem:
        """Parse a Plex metadata dict into a MediaItem."""
        # Extract TMDB/IMDB ID from GUIDs
        tmdb_id = None
        imdb_id = None
        for g in m.get("Guid", []):
            gid = g.get("id", "")
            if gid.startswith("tmdb://"):
                try:
                    tmdb_id = int(gid.replace("tmdb://", ""))
                except ValueError:
                    pass
            elif gid.startswith("imdb://"):
                imdb_id = gid.replace("imdb://", "")

        genres = [g.get("tag", "") for g in m.get("Genre", [])]

        return MediaItem(
            plex_key=m.get("ratingKey", ""),
            title=m.get("title", ""),
            year=m.get("year"),
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            media_type="movie" if m.get("type") == "movie" else "show",
            library_id=library_id or m.get("librarySectionID"),
            poster_url=f"{self.url}{m['thumb']}?X-Plex-Token={self.token}" if m.get("thumb") else None,
            genres=genres,
            duration_ms=m.get("duration"),
            added_at=datetime.fromtimestamp(m["addedAt"]) if m.get("addedAt") else None,
        )
