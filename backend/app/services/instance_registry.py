"""Servarr instance registry — N-instance Radarr/Sonarr management.

Manages a dynamic list of Radarr/Sonarr instances, stored in the
settings_store (SQLite). Bootstrap from .env on first startup,
then fully manageable via API without container restarts.

Each instance has:
  - name: unique identifier (e.g. "radarr", "sonarr_anime")
  - type: "radarr" or "sonarr"
  - url: base URL
  - api_key: API key
  - is_default_for: optional domain default ("movie", "tv", or null)

The routing engine (MediaRouter) decides which instance handles a
request based on genre/keyword rules. The registry just holds the
client pool — routing logic stays in media_router.py.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient

logger = logging.getLogger(__name__)


@dataclass
class InstanceConfig:
    """Configuration for a single Radarr/Sonarr instance."""
    name: str
    type: str            # "radarr" | "sonarr"
    url: str
    api_key: str
    is_default_for: Optional[str] = None  # "movie" | "tv" | None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "api_key": self.api_key,
            "is_default_for": self.is_default_for,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InstanceConfig":
        return cls(
            name=d["name"],
            type=d["type"],
            url=d["url"],
            api_key=d["api_key"],
            is_default_for=d.get("is_default_for"),
        )


class InstanceRegistry:
    """Pool of live Radarr/Sonarr client instances.

    Built from InstanceConfig list. Provides lookup by name,
    by type, and default-for-domain queries.
    """

    def __init__(self):
        self._configs: list[InstanceConfig] = []
        self._clients: dict[str, RadarrClient | SonarrClient] = {}

    @property
    def configs(self) -> list[InstanceConfig]:
        return list(self._configs)

    def get(self, name: str) -> RadarrClient | SonarrClient | None:
        """Get a client by instance name."""
        return self._clients.get(name)

    def get_by_type(self, inst_type: str) -> list[tuple[str, RadarrClient | SonarrClient]]:
        """Get all instances of a given type. Returns [(name, client), ...]."""
        return [
            (cfg.name, self._clients[cfg.name])
            for cfg in self._configs
            if cfg.type == inst_type and cfg.name in self._clients
        ]

    def get_default_for(self, domain: str) -> RadarrClient | SonarrClient | None:
        """Get the default instance for a media domain ("movie" or "tv").

        Falls back to first instance of the matching type if no default set.
        """
        for cfg in self._configs:
            if cfg.is_default_for == domain and cfg.name in self._clients:
                return self._clients[cfg.name]
        # Fallback: first radarr for movie, first sonarr for tv
        fallback_type = "radarr" if domain == "movie" else "sonarr"
        for cfg in self._configs:
            if cfg.type == fallback_type and cfg.name in self._clients:
                return self._clients[cfg.name]
        return None

    def get_config(self, name: str) -> InstanceConfig | None:
        """Get config for an instance by name."""
        for cfg in self._configs:
            if cfg.name == name:
                return cfg
        return None

    def all_names(self) -> list[str]:
        return [cfg.name for cfg in self._configs]

    def build_from_configs(self, configs: list[InstanceConfig]) -> None:
        """Create live clients from config list."""
        self._configs = configs
        self._clients = {}
        for cfg in configs:
            try:
                if cfg.type == "radarr":
                    self._clients[cfg.name] = RadarrClient(url=cfg.url, api_key=cfg.api_key)
                elif cfg.type == "sonarr":
                    self._clients[cfg.name] = SonarrClient(url=cfg.url, api_key=cfg.api_key)
                else:
                    logger.warning(f"Unknown instance type '{cfg.type}' for '{cfg.name}'")
                    continue
                logger.info(f"Registered {cfg.type} instance '{cfg.name}' → {cfg.url}")
            except Exception as e:
                logger.error(f"Failed to create client for '{cfg.name}': {e}")

    def rebuild_instance(self, name: str, cfg: InstanceConfig) -> None:
        """Hot-swap a single instance (for settings updates without restart)."""
        # Remove old
        self._configs = [c for c in self._configs if c.name != name]
        self._clients.pop(name, None)
        # Add new
        self._configs.append(cfg)
        if cfg.type == "radarr":
            self._clients[cfg.name] = RadarrClient(url=cfg.url, api_key=cfg.api_key)
        elif cfg.type == "sonarr":
            self._clients[cfg.name] = SonarrClient(url=cfg.url, api_key=cfg.api_key)
        logger.info(f"Rebuilt {cfg.type} instance '{cfg.name}' → {cfg.url}")

    def remove_instance(self, name: str) -> bool:
        """Remove an instance. Returns True if found and removed."""
        if name not in self._clients:
            return False
        self._configs = [c for c in self._configs if c.name != name]
        self._clients.pop(name, None)
        logger.info(f"Removed instance '{name}'")
        return True


def load_instance_configs() -> list[InstanceConfig]:
    """Load instance configs from settings_store, bootstrapping from .env if needed."""
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    saved = store.get("servarr_instances")

    if saved and isinstance(saved, list) and len(saved) > 0:
        configs = [InstanceConfig.from_dict(d) for d in saved]
        logger.info(f"Loaded {len(configs)} servarr instances from settings store")
        return configs

    # Bootstrap from .env (first startup or migration)
    configs = _bootstrap_from_env()
    if configs:
        store.set("servarr_instances", [c.to_dict() for c in configs])
        logger.info(f"Bootstrapped {len(configs)} servarr instances from .env → settings store")
    return configs


def save_instance_configs(configs: list[InstanceConfig]) -> None:
    """Persist instance configs to settings_store."""
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    store.set("servarr_instances", [c.to_dict() for c in configs])


def _bootstrap_from_env() -> list[InstanceConfig]:
    """Create initial instance configs from legacy .env variables."""
    from app.config import settings
    configs = []

    if settings.radarr_url and settings.radarr_api_key:
        configs.append(InstanceConfig(
            name="radarr", type="radarr",
            url=settings.radarr_url, api_key=settings.radarr_api_key,
            is_default_for="movie",
        ))

    if settings.sonarr_url and settings.sonarr_api_key:
        configs.append(InstanceConfig(
            name="sonarr_tv", type="sonarr",
            url=settings.sonarr_url, api_key=settings.sonarr_api_key,
            is_default_for="tv",
        ))

    if settings.sonarr_anime_url and settings.sonarr_anime_api_key:
        configs.append(InstanceConfig(
            name="sonarr_anime", type="sonarr",
            url=settings.sonarr_anime_url, api_key=settings.sonarr_anime_api_key,
        ))

    return configs
