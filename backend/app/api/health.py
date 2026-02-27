"""Health and system status endpoints."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    """Service health check — reports integration status."""
    integrations = getattr(request.app.state, "integrations", {})
    return {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "integrations": integrations,
    }


@router.get("/stats")
async def system_stats():
    """System statistics — profiles, embeddings, cache status."""
    # TODO: implement after services are built
    return {
        "users": 0,
        "embeddings": 0,
        "tmdb_cache_entries": 0,
        "recommendations_generated": 0,
    }
