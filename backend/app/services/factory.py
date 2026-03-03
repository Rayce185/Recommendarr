"""Service factory — single place to construct the full client + service stack.

All clients are initialized once at startup and shared across requests.
No per-request DB session needed for the core recommendation flow.
"""

import logging
from dataclasses import dataclass

from app.config import settings
from app.clients.tautulli import TautulliClient
from app.clients.seerr import SeerrClient
from app.clients.servarr import RadarrClient, SonarrClient
from app.clients.plex import PlexClient
from app.clients.tmdb import TMDBClient
from app.services.taste_profiler import TasteProfiler
from app.services.recommender import RecommendationEngine

logger = logging.getLogger(__name__)


@dataclass
class ServiceStack:
    """All initialized clients and services, ready for injection."""
    tautulli: TautulliClient
    seerr: SeerrClient
    radarr: RadarrClient
    sonarr_tv: SonarrClient
    sonarr_anime: SonarrClient
    profiler: TasteProfiler
    engine: RecommendationEngine
    plex: PlexClient | None = None
    tmdb: 'TMDBClient | None' = None

    # User ID → username mapping (populated at startup from Tautulli)
    user_map: dict[str, str] = None          # numeric_id → username
    user_reverse_map: dict[str, str] = None  # username → numeric_id


_stack: ServiceStack | None = None


def build_stack() -> ServiceStack:
    """Construct the full service stack from config settings."""
    global _stack

    tautulli = TautulliClient(
        url=settings.tautulli_url,
        api_key=settings.tautulli_api_key,
    )

    seerr = SeerrClient(
        url=settings.seerr_url,
        api_key=settings.seerr_api_key,
    )

    radarr = RadarrClient(
        url=settings.radarr_url,
        api_key=settings.radarr_api_key,
    )

    sonarr_tv = SonarrClient(
        url=settings.sonarr_url,
        api_key=settings.sonarr_api_key,
    )

    sonarr_anime = SonarrClient(
        url=settings.sonarr_anime_url,
        api_key=settings.sonarr_anime_api_key,
    )

    # Plex (optional — for deep links)
    plex = None
    if settings.plex_url and settings.plex_token:
        plex = PlexClient(
            url=settings.plex_url,
            token=settings.plex_token,
        )
        if settings.plex_machine_id:
            plex.machine_id = settings.plex_machine_id
        logger.info("Plex client configured")

    # TMDB (direct API for expanded trending)
    tmdb = None
    if settings.tmdb_api_key:
        tmdb = TMDBClient(api_key=settings.tmdb_api_key)
        logger.info("TMDB client configured")

    profiler = TasteProfiler(
        tautulli=tautulli,
        seerr=seerr,
    )

    engine = RecommendationEngine(
        tautulli=tautulli,
        seerr=seerr,
        radarr=radarr,
        sonarr_tv=sonarr_tv,
        sonarr_anime=sonarr_anime,
        profiler=profiler,
    )

    _stack = ServiceStack(
        tautulli=tautulli,
        seerr=seerr,
        radarr=radarr,
        sonarr_tv=sonarr_tv,
        sonarr_anime=sonarr_anime,
        profiler=profiler,
        engine=engine,
        plex=plex,
        tmdb=tmdb,
    )

    logger.info("Service stack initialized")
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
    """Resolve a numeric Tautulli user_id to a username."""
    s = stack or get_stack()
    if s.user_map:
        return s.user_map.get(str(user_id), str(user_id))
    return str(user_id)


def resolve_user_id(username: str, stack: ServiceStack | None = None) -> str:
    """Resolve a username to a numeric Tautulli user_id."""
    s = stack or get_stack()
    if s.user_reverse_map:
        return s.user_reverse_map.get(username, username)
    return username
