"""Recommendarr v2 — FastAPI application entry point.

API-first architecture: no local DB required for core recommendation flow.
All data sourced live from Tautulli + Seerr + Radarr/Sonarr APIs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import health_v2, users_v2, recommendations_v2, auth, refresh, feedback
from app.api import settings as settings_api
from app.services.factory import build_stack, init_user_map

# ── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("recommendarr")


# ── App lifecycle ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: build service stack, probe integrations, load user map."""
    logger.info("=== Recommendarr v2 starting ===")
    logger.info(f"Architecture: API-first (no embeddings, no local DB for recs)")

    # Build all clients and services
    stack = build_stack()

    # Probe all upstream services
    probes = {}
    try:
        probes["tautulli"] = await stack.tautulli.test_connection()
    except Exception:
        probes["tautulli"] = False
    try:
        probes["seerr"] = await stack.seerr.test_connection()
    except Exception:
        probes["seerr"] = False
    try:
        probes["radarr"] = await stack.radarr.test_connection()
    except Exception:
        probes["radarr"] = False
    try:
        probes["sonarr_tv"] = await stack.sonarr_tv.test_connection()
    except Exception:
        probes["sonarr_tv"] = False
    try:
        probes["sonarr_anime"] = await stack.sonarr_anime.test_connection()
    except Exception:
        probes["sonarr_anime"] = False

    # Plex (optional — for deep links)
    if stack.plex:
        try:
            probes["plex"] = await stack.plex.test_connection()
            if probes["plex"]:
                if not stack.plex.machine_id:
                    await stack.plex.init()
                await stack.plex.build_tmdb_map()
                logger.info(f"Plex TMDB map: {stack.plex.map_size} items indexed")
        except Exception as e:
            probes["plex"] = False
            logger.warning(f"Plex init failed: {e}")
    else:
        logger.info("Plex not configured — deep links disabled")

    ok_count = sum(1 for v in probes.values() if v)
    logger.info(f"Service probes: {ok_count}/{len(probes)} OK — {probes}")

    if not probes.get("tautulli"):
        logger.error("CRITICAL: Tautulli not reachable — watch history unavailable")
    if not probes.get("seerr"):
        logger.error("CRITICAL: Seerr not reachable — metadata enrichment unavailable")

    # Load user ID ↔ username mapping
    await init_user_map(stack)

    logger.info("=== Recommendarr v2 ready ===")
    yield
    logger.info("=== Recommendarr v2 shutting down ===")


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Recommendarr",
    version="0.2.0",
    description="Personal media recommendation engine — API-first, zero GPU",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        f"http://localhost:{settings.recommendarr_port}",
        f"http://192.168.0.111:{settings.recommendarr_port}",
        "https://recommendarr.mydirenzo.ch",
        "*",  # Dev mode — tighten for production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount v2 routers ─────────────────────────────────────────────

app.include_router(health_v2.router,            prefix="/api/v1", tags=["system"])
app.include_router(users_v2.router,             prefix="/api/v1", tags=["users"])
app.include_router(recommendations_v2.router,   prefix="/api/v1", tags=["recommendations"])
app.include_router(auth.router,                 prefix="/api/v1", tags=["auth"])
app.include_router(refresh.router,              prefix="/api/v1", tags=["cache"])
app.include_router(feedback.router,             prefix="/api/v1", tags=["feedback"])
app.include_router(settings_api.router,        prefix="/api/v1/system", tags=["settings"])


@app.get("/")
async def root():
    return {
        "name": "Recommendarr",
        "version": "0.2.0",
        "docs": "/api/docs",
        "health": "/api/v1/health",
    }
