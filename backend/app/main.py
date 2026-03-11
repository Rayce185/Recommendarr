"""Recommendarr — FastAPI application entry point.

SQLite DB for persistence, TMDB for metadata, Radarr/Sonarr for library.
Optional ChromaDB sync for RAG pipeline integration.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.startup import lifespan

# ── Structured Logging (D2) ───────────────────────────────────────

from app.middleware.logging_config import setup_logging, RequestIDMiddleware

setup_logging(settings.log_level)

# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Recommendarr",
    version="1.1.0-dev",
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

# ── Rate Limiting (D1) ───────────────────────────────────────────

from app.middleware.rate_limit import setup_rate_limiting

setup_rate_limiting(app)

# ── Request ID Middleware (D2) ────────────────────────────────────

app.add_middleware(RequestIDMiddleware)

# ── Mount API routers ────────────────────────────────────────────

from app.api import health, users, recommendations, auth, refresh, feedback
from app.api import settings as settings_api
from app.api import ai_settings, watchlist, library
from app.api import instances as instances_api
from app.api import discovery, discovery_extras, media_requests, collections_routes
from app.api import schedule, browse, wrapped, social, list_import, cultural_pulse
from app.api import rec_mood
from app.api import why_not
from app.api import calendar
from app.api import profile_transfer
from app.api import notifications
from app.api import history
from app.api import setup, webhooks
from app.api import group_night
from app.api import admin_users
from app.api import series_progress
from app.api import friends
from app.api import library_health
from app.api import library_health_admin
from app.api import push
from app.api import compare

app.include_router(health.router,                prefix="/api/v1", tags=["system"])
app.include_router(users.router,                 prefix="/api/v1", tags=["users"])
app.include_router(recommendations.router,       prefix="/api/v1", tags=["recommendations"])
app.include_router(rec_mood.router,              prefix="/api/v1", tags=["recommendations"])
app.include_router(why_not.router,               prefix="/api/v1", tags=["recommendations"])
app.include_router(auth.router,                  prefix="/api/v1", tags=["auth"])
app.include_router(refresh.router,               prefix="/api/v1", tags=["cache"])
app.include_router(feedback.router,              prefix="/api/v1", tags=["feedback"])
app.include_router(settings_api.router,          prefix="/api/v1/system", tags=["settings"])
app.include_router(ai_settings.router,           prefix="/api/v1/system", tags=["AI"])
app.include_router(watchlist.router,             prefix="/api/v1", tags=["watchlist"])
app.include_router(library.router,               prefix="/api/v1", tags=["library"])
app.include_router(instances_api.router,         prefix="/api/v1/system", tags=["instances"])
app.include_router(browse.router,                prefix="/api/v1", tags=["browse"])
app.include_router(wrapped.router,               prefix="/api/v1", tags=["wrapped"])
app.include_router(social.router,                prefix="/api/v1", tags=["social"])
app.include_router(schedule.router,              prefix="/api/v1", tags=["schedule"])
app.include_router(list_import.router,           prefix="/api/v1", tags=["import"])
app.include_router(cultural_pulse.router,        prefix="/api/v1", tags=["pulse"])
app.include_router(discovery.router,             prefix="/api/v1", tags=["discovery"])
app.include_router(discovery_extras.router,      prefix="/api/v1", tags=["discovery"])
app.include_router(media_requests.router,        prefix="/api/v1", tags=["requests"])
app.include_router(collections_routes.router,    prefix="/api/v1", tags=["collections"])
app.include_router(calendar.router,              prefix="/api/v1", tags=["calendar"])
app.include_router(profile_transfer.router, prefix="/api/v1", tags=["profile"])
app.include_router(notifications.router,      prefix="/api/v1", tags=["notifications"])
app.include_router(history.router,            prefix="/api/v1", tags=["history"])
app.include_router(friends.router,            prefix="/api/v1", tags=["social"])
app.include_router(setup.router,             prefix="/api/v1", tags=["setup"])
app.include_router(webhooks.router,          prefix="/api/v1", tags=["webhooks"])
app.include_router(group_night.router,       prefix="/api/v1", tags=["group-night"])
app.include_router(admin_users.router,       prefix="/api/v1", tags=["admin"])
app.include_router(series_progress.router, prefix="/api/v1", tags=["users"])
app.include_router(library_health.router,    prefix="/api/v1", tags=["library-health"])
app.include_router(library_health_admin.router, prefix="/api/v1", tags=["library-health"])
app.include_router(push.router,                   prefix="/api/v1", tags=["push"])
app.include_router(compare.router,                prefix="/api/v1", tags=["compare"])

# ── Static files (frontend) ──────────────────────────────────────

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
        return {"name": "Recommendarr", "version": "1.0.0", "docs": "/api/docs"}
