"""Service factory — constructs the full client + service stack at startup.

Uses the instance registry for N-instance Radarr/Sonarr support.
Legacy properties (radarr, sonarr_tv, sonarr_anime) delegate to the
registry for backward compatibility.
"""

import logging
from dataclasses import dataclass, field

from app.config import settings
from app.clients.tautulli import TautulliClient
from app.clients.seerr import SeerrClient
from app.clients.plex import PlexClient
from app.clients.tmdb import TMDBClient
from app.services.taste_profiler import TasteProfiler
from app.services.recommender import RecommendationEngine
from app.services.instance_registry import (
    InstanceRegistry, load_instance_configs,
)

logger = logging.getLogger(__name__)


@dataclass
class ServiceStack:
    """All initialized clients and services, ready for injection."""
    tautulli: TautulliClient
    seerr: SeerrClient
    registry: InstanceRegistry
    profiler: TasteProfiler
    engine: RecommendationEngine
    plex: PlexClient | None = None
    tmdb: TMDBClient | None = None

    # User ID → username mapping (populated at startup from Tautulli)
    user_map: dict[str, str] = None
    user_reverse_map: dict[str, str] = None

    # ── Backward-compat properties ───────────────────────────────
    # These delegate to the registry so existing code doesn't break.
    # New code should use stack.registry.get("instance_name") directly.

    @property
    def radarr(self):
        """Default Radarr instance (backward compat)."""
        client = self.registry.get_default_for("movie")
        if not client:
            raise RuntimeError("No Radarr instance configured")
        return client

    @property
    def sonarr_tv(self):
        """Default Sonarr TV instance (backward compat)."""
        # Try named instance first, then default-for-tv
        client = self.registry.get("sonarr_tv")
        if not client:
            client = self.registry.get_default_for("tv")
        if not client:
            raise RuntimeError("No Sonarr TV instance configured")
        return client

    @property
    def sonarr_anime(self):
        """Sonarr Anime instance (backward compat)."""
        client = self.registry.get("sonarr_anime")
        if not client:
            # Fallback: any sonarr instance that isn't the TV default
            for name, c in self.registry.get_by_type("sonarr"):
                if name != "sonarr_tv":
                    return c
        if not client:
            raise RuntimeError("No Sonarr Anime instance configured")
        return client


_stack: ServiceStack | None = None


def build_stack() -> ServiceStack:
    """Construct the full service stack from config + instance registry."""
    global _stack

    tautulli = TautulliClient(
        url=settings.tautulli_url,
        api_key=settings.tautulli_api_key,
    )

    seerr = SeerrClient(
        url=settings.seerr_url,
        api_key=settings.seerr_api_key,
    )

    # Build instance registry (N Radarr/Sonarr instances)
    registry = InstanceRegistry()
    configs = load_instance_configs()
    registry.build_from_configs(configs)

    # Plex (optional)
    plex = None
    if settings.plex_url and settings.plex_token:
        plex = PlexClient(url=settings.plex_url, token=settings.plex_token)
        if settings.plex_machine_id:
            plex.machine_id = settings.plex_machine_id
        logger.info("Plex client configured")

    # TMDB (direct API)
    tmdb = None
    if settings.tmdb_api_key:
        tmdb = TMDBClient(api_key=settings.tmdb_api_key)
        logger.info("TMDB client configured")

    profiler = TasteProfiler(
        tautulli=tautulli, seerr=seerr, tmdb=tmdb,
    )

    # Build engine — uses registry backward-compat properties
    # Will refactor engine to use registry directly later
    _stack_temp = ServiceStack(
        tautulli=tautulli, seerr=seerr, registry=registry,
        profiler=profiler, engine=None, plex=plex, tmdb=tmdb,
    )

    engine = RecommendationEngine(
        tautulli=tautulli, seerr=seerr,
        radarr=_stack_temp.radarr if registry.get_by_type("radarr") else None,
        sonarr_tv=_stack_temp.sonarr_tv if registry.get("sonarr_tv") or registry.get_default_for("tv") else None,
        sonarr_anime=_stack_temp.sonarr_anime if registry.get("sonarr_anime") else None,
        profiler=profiler, tmdb=tmdb,
    )

    _stack = ServiceStack(
        tautulli=tautulli, seerr=seerr, registry=registry,
        profiler=profiler, engine=engine, plex=plex, tmdb=tmdb,
    )

    inst_summary = ", ".join(
        f"{c.name} ({c.type})" for c in configs
    )
    logger.info(f"Service stack initialized — instances: [{inst_summary}]")
    return _stack


async def init_user_map(stack: ServiceStack):
    """Populate user ID ↔ username mapping from Tautulli."""
    try:
        users = await stack.tautulli.get_users()
        stack.user_map = {}
        stack.user_reverse_map = {}
        for u in users:
            uid = str(u.get("user_id", ""))
            uname = u.get("username", "") or u.get("friendly_name", "")
            if uid and uname:
                stack.user_map[uid] = uname
                stack.user_reverse_map[uname] = uid
        logger.info(f"User map loaded: {len(stack.user_map)} users")
    except Exception as e:
        logger.error(f"Failed to load user map: {e}")
        stack.user_map = {}
        stack.user_reverse_map = {}


def get_stack() -> ServiceStack:
    """Get the initialized service stack."""
    if _stack is None:
        raise RuntimeError("Service stack not initialized — call build_stack() first")
    return _stack


def resolve_username(user_id: str, stack: ServiceStack | None = None) -> str:
    s = stack or get_stack()
    if s.user_map:
        return s.user_map.get(str(user_id), str(user_id))
    return str(user_id)


def resolve_user_id(username: str, stack: ServiceStack | None = None) -> str:
    s = stack or get_stack()
    if s.user_reverse_map:
        return s.user_reverse_map.get(username, username)
    return username
