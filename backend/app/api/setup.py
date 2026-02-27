"""Onboarding wizard and setup endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.database import get_db

router = APIRouter()


class ConnectionTest(BaseModel):
    type: str          # plex | tautulli | radarr | sonarr | seerr | ollama | tmdb
    url: str
    api_key: Optional[str] = None
    token: Optional[str] = None


@router.get("/setup/status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    """Check which setup steps have been completed."""
    # TODO: check if server connected, integrations configured, any users onboarded
    return {
        "server_connected": False,
        "integrations_configured": False,
        "users_synced": False,
        "first_user_onboarded": False,
    }


@router.post("/setup/integrations/test")
async def test_integration(conn: ConnectionTest):
    """Test connection to any integration (Plex, Radarr, Tautulli, etc.)."""
    # TODO: probe the service, return success/failure with details
    return {
        "type": conn.type,
        "url": conn.url,
        "reachable": False,
        "authenticated": False,
        "details": None,
    }
