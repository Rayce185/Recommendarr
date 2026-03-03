"""Abstract interfaces for media server and watch history providers.

These define the contracts that all media server implementations must follow.
Plex is the Phase 1 implementation. Jellyfin/Emby/Kodi are community contributions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── Data Transfer Objects ────────────────────────────────────────

@dataclass
class MediaLibrary:
    """A library/section from the media server."""
    id: str
    name: str
    type: str              # "movie" | "show"
    item_count: int = 0


@dataclass
class MediaItem:
    """A single media item (movie or episode)."""
    plex_key: str          # Server-specific key
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    media_type: str = "movie"
    library_id: Optional[str] = None
    poster_url: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    duration_ms: Optional[int] = None
    added_at: Optional[datetime] = None
    # Playback quality info
    video_codec: Optional[str] = None
    video_resolution: Optional[str] = None
    audio_codec: Optional[str] = None
    hdr_type: Optional[str] = None       # "HDR10" | "Dolby Vision" | None


@dataclass
class WatchEvent:
    """A single watch event from history."""
    user_id: str           # Server-specific user ID
    item_key: str          # Server-specific item key
    tmdb_id: Optional[int] = None
    media_type: str = "movie"
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    duration_seconds: int = 0
    total_duration_seconds: int = 0
    completion_pct: float = 0.0
    watch_count: int = 1
    user_rating: Optional[float] = None


@dataclass
class ServerUser:
    """A user on the media server."""
    id: str                # Server-specific user ID
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    thumb_url: Optional[str] = None
    is_admin: bool = False
    accessible_library_ids: list[str] = field(default_factory=list)


@dataclass
class PlaybackClient:
    """An active playback device/client."""
    id: str
    name: str
    platform: Optional[str] = None     # "webos" | "android" | "windows" | etc.
    state: str = "idle"                # "idle" | "playing" | "paused"
    controllable: bool = False
    current_item_key: Optional[str] = None


# ── Abstract Interfaces ──────────────────────────────────────────

class IMediaServer(ABC):
    """Interface for media server backends (Plex, Jellyfin, Emby, Kodi)."""

    @abstractmethod
    async def get_libraries(self) -> list[MediaLibrary]:
        """List all libraries on the server."""
        ...

    @abstractmethod
    async def get_library_items(self, library_id: str) -> list[MediaItem]:
        """Get all items in a specific library."""
        ...

    @abstractmethod
    async def get_item(self, item_key: str) -> Optional[MediaItem]:
        """Get a single item by its server key."""
        ...

    @abstractmethod
    async def get_users(self) -> list[ServerUser]:
        """Get all users with their library access permissions."""
        ...

    @abstractmethod
    async def get_user_ratings(self, user_id: str) -> list[tuple[str, float]]:
        """Get user ratings as (item_key, rating) pairs."""
        ...

    @abstractmethod
    async def get_clients(self) -> list[PlaybackClient]:
        """Get active playback clients/devices."""
        ...

    @abstractmethod
    async def play_on_device(self, device_id: str, item_key: str, resume: bool = False) -> bool:
        """Start playback on a specific client."""
        ...

    @abstractmethod
    async def create_playlist(self, user_id: str, title: str, item_keys: list[str]) -> Optional[str]:
        """Create a playlist for a user. Returns playlist key."""
        ...

    @abstractmethod
    async def create_collection(self, library_id: str, title: str, item_keys: list[str]) -> Optional[str]:
        """Create a collection in a library. Returns collection key."""
        ...

    @abstractmethod
    async def get_media_info(self, item_key: str) -> Optional[MediaItem]:
        """Get detailed media info (codecs, resolution, HDR, audio)."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the server is reachable and authenticated."""
        ...


class IWatchHistoryProvider(ABC):
    """Interface for watch history sources (Tautulli, Jellyfin API, Emby API)."""

    @abstractmethod
    async def get_history(
        self,
        user_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[WatchEvent]:
        """Pull watch history. Optionally filter by user and/or date."""
        ...

    @abstractmethod
    async def get_most_watched(self, user_id: str, limit: int = 50) -> list[WatchEvent]:
        """Top N most-watched items for a user."""
        ...

    @abstractmethod
    async def supports_webhooks(self) -> bool:
        """Whether this provider can push events in real-time."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the provider is reachable."""
        ...
