"""Recommendarr — FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import health, users, recommendations, webhooks, setup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: initialize DB pool, probe integrations
    from app.database import init_db
    from app.services.integration_probe import probe_all

    await init_db()
    app.state.integrations = await probe_all(settings)
    yield
    # Shutdown: close DB pool, cleanup


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-powered personal media recommendation engine",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# CORS — allow frontend dev server + production URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",     # Vite dev server
        "http://localhost:30800",    # Production
        settings.app_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ────────────────────────────────────────────────
app.include_router(health.router,           prefix="/api/v1", tags=["system"])
app.include_router(users.router,            prefix="/api/v1", tags=["users"])
app.include_router(recommendations.router,  prefix="/api/v1", tags=["recommendations"])
app.include_router(webhooks.router,         prefix="/api/v1", tags=["webhooks"])
app.include_router(setup.router,            prefix="/api/v1", tags=["setup"])
