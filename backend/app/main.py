"""Recommendarr — FastAPI application entry point.

SQLite DB for persistence, TMDB for metadata, Radarr/Sonarr for library.
Optional ChromaDB sync for RAG pipeline integration.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.config import settings
from app.api import health, users, recommendations, auth, refresh, feedback
from app.api import settings as settings_api
from app.api import ai_settings
from app.api import watchlist
from app.api import library
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
    """Startup: init DB, migrate data, build service stack, probe integrations."""
    logger.info("=== Recommendarr starting ===")

    # Initialize SQLite database + run migrations
    from app.database import init_db
    init_db()

    from app.services.db_migrate import migrate_json_to_sqlite
    migrate_json_to_sqlite()

    # Initialize ChromaDB sync (optional — only if configured)
    from app.services.chroma_sync import init_chroma_sync
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    chromadb_url = store.get("chromadb_url") or settings.chromadb_url
    embed_url = store.get("llm_base_url") or settings.llm_base_url
    embed_model = store.get("embedding_model") or settings.embedding_model
    if chromadb_url and embed_url:
        sync = init_chroma_sync(chromadb_url, embed_url, embed_model)
        if sync:
            logger.info(f"ChromaDB sync enabled → {chromadb_url}")
    else:
        logger.info("ChromaDB sync disabled (no chromadb_url configured)")

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
        logger.warning("Seerr not reachable — using TMDB direct for metadata")

    # Load user ID ↔ username mapping
    await init_user_map(stack)

    logger.info("=== Recommendarr ready ===")

    # Background: pre-warm taste profiles so first page load is instant
    import asyncio
    async def _warm_profiles():
        try:
            await asyncio.sleep(2)
            from app.services.factory import get_stack
            from app.services.cache import get_cache
            import time as _t
            s = get_stack()
            if not s.profiler or not s.user_map:
                return
            cache = get_cache()
            # Warm top 3 users (covers admin + most active)
            active = list(s.user_map.values())[:3]
            warmed = 0
            for username in active:
                if cache.get_profile(username, "all") is not None:
                    continue
                try:
                    _start = _t.monotonic()
                    profile = await s.profiler.build_profile(
                        username=username, domain="all",
                        depth_months=24, enrich_keywords=True, max_enrich=100,
                    )
                    cache.set_profile(username, "all", profile)
                    warmed += 1
                    logger.info(f"Profile warmed: {username} ({profile.total_watched} titles, {_t.monotonic()-_start:.1f}s)")
                except Exception as e:
                    logger.warning(f"Profile warming failed for {username}: {e}")
            # Also warm library candidates (Radarr/Sonarr fetch)
            try:
                _start = _t.monotonic()
                await s.engine._get_library_candidates("all")
                logger.info(f"Library cache warmed ({_t.monotonic()-_start:.1f}s)")
            except Exception as e:
                logger.debug(f"Library warming skipped: {e}")

            # Pre-warm recommendation results (includes AI explanations)
            if warmed > 0:
                from app.services.recommender import RecommendationRequest
                for username in active:
                    if not cache.get_profile(username, "all"):
                        continue  # Skip users with no profile
                    for mode in ["tonight", "grab"]:
                        try:
                            _start = _t.monotonic()
                            req = RecommendationRequest(
                                username=username, mode=mode, domain="all",
                                limit=30,
                            )
                            results = await s.engine.recommend(req)
                            if results:
                                from dataclasses import asdict
                                recs_data = []
                                for r in results:
                                    try:
                                        recs_data.append(asdict(r))
                                    except Exception:
                                        recs_data.append(r.__dict__ if hasattr(r, "__dict__") else {})
                                cache.set_recs(username, mode, "all", {
                                    "recommendations": recs_data,
                                    "meta": {"username": username, "mode": mode, "count": len(results)},
                                })
                                logger.info(f"Recs warmed: {username}/{mode} ({len(results)} items, {_t.monotonic()-_start:.1f}s)")
                        except Exception as e:
                            logger.warning(f"Rec warming failed for {username}/{mode}: {e}")

            if warmed:
                logger.info(f"Startup warming done: {warmed} profiles + library + recs cached")
        except Exception as e:
            logger.warning(f"Profile warming error: {e}")

    asyncio.create_task(_warm_profiles())

    yield
    # Cleanup ChromaDB sync
    from app.services.chroma_sync import get_chroma_sync
    sync = get_chroma_sync()
    if sync:
        await sync.close()
    logger.info("=== Recommendarr shutting down ===")


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Recommendarr",
    version="0.5.0",
    description="Personal media recommendation engine — SQLite + TMDB + ChromaDB RAG",
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

app.include_router(health.router,            prefix="/api/v1", tags=["system"])
app.include_router(users.router,             prefix="/api/v1", tags=["users"])
app.include_router(recommendations.router,   prefix="/api/v1", tags=["recommendations"])
app.include_router(auth.router,                 prefix="/api/v1", tags=["auth"])
app.include_router(refresh.router,              prefix="/api/v1", tags=["cache"])
app.include_router(feedback.router,             prefix="/api/v1", tags=["feedback"])
app.include_router(settings_api.router,        prefix="/api/v1/system", tags=["settings"])
app.include_router(ai_settings.router,          prefix="/api/v1/system", tags=["AI"])
app.include_router(watchlist.router,             prefix="/api/v1", tags=["watchlist"])
app.include_router(library.router,               prefix="/api/v1", tags=["library"])


# ── Static files (frontend) ───────────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    _assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React SPA — all non-API routes return index.html."""
        if full_path:
            file_path = os.path.join(STATIC_DIR, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
else:
    @app.get("/")
    async def root():
        return {"name": "Recommendarr", "version": "0.5.0", "docs": "/api/docs"}
