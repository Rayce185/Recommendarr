"""Onboarding wizard and setup endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

from app.services.factory import get_stack
from app.services.settings_store import get_settings_store
from app.auth.jwt_handler import TokenPayload, get_current_user

router = APIRouter()

SAVEABLE_FIELDS = {
    "tmdb_api_key", "tautulli_url", "tautulli_api_key",
    "radarr_url", "radarr_api_key", "sonarr_url", "sonarr_api_key",
    "sonarr_anime_url", "sonarr_anime_api_key", "seerr_url", "seerr_api_key",
}


class ConnectionTest(BaseModel):
    type: str
    url: str
    api_key: Optional[str] = None
    token: Optional[str] = None


class SetupSettings(BaseModel):
    settings: dict[str, str]


@router.get("/setup/status")
async def setup_status():
    """Check which setup steps have been completed by probing real state."""
    stack = get_stack()
    store = get_settings_store()

    onboarding_complete = store.get("onboarding_complete", False)

    server_connected = False
    if stack.plex:
        try:
            server_connected = await stack.plex.test_connection()
        except Exception:
            pass

    from app.config import settings as cfg
    tmdb_configured = bool(cfg.tmdb_api_key)

    integrations = {}
    for name, getter in [
        ("tautulli", lambda: stack.tautulli),
        ("radarr", lambda: stack.radarr),
        ("sonarr_tv", lambda: stack.sonarr_tv),
        ("seerr", lambda: stack.seerr),
    ]:
        try:
            client = getter()
            integrations[name] = await client.test_connection()
        except Exception:
            integrations[name] = False

    users_synced = bool(stack.user_map and len(stack.user_map) > 0)

    return {
        "onboarding_complete": onboarding_complete,
        "server_connected": server_connected,
        "tmdb_configured": tmdb_configured,
        "integrations_detail": integrations,
        "users_synced": users_synced,
        "user_count": len(stack.user_map) if stack.user_map else 0,
        "complete": onboarding_complete or all([
            server_connected, tmdb_configured, users_synced,
        ]),
    }


@router.post("/setup/integrations/test")
async def test_integration(conn: ConnectionTest):
    """Test connection to any integration."""
    url = conn.url.rstrip("/")

    probe_paths = {
        "plex": "/",
        "tautulli": "/api/v2",
        "radarr": "/api/v3/system/status",
        "sonarr": "/api/v3/system/status",
        "seerr": "/api/v1/status",
        "ollama": "/api/tags",
        "tmdb": "/3/configuration",
    }

    path = probe_paths.get(conn.type, "/")
    probe_url = f"{url}{path}"

    headers = {}
    if conn.type == "plex" and conn.token:
        headers["X-Plex-Token"] = conn.token
    elif conn.type in ("radarr", "sonarr") and conn.api_key:
        headers["X-Api-Key"] = conn.api_key
    elif conn.type == "tautulli" and conn.api_key:
        probe_url = f"{url}/api/v2?apikey={conn.api_key}&cmd=arnold"
    elif conn.type == "tmdb" and conn.api_key:
        probe_url = f"{url}{path}?api_key={conn.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(probe_url, headers=headers)
            reachable = resp.status_code < 500
            authenticated = resp.status_code not in (401, 403)
            return {
                "type": conn.type,
                "url": url,
                "reachable": reachable,
                "authenticated": authenticated,
                "status_code": resp.status_code,
                "details": None,
            }
    except httpx.ConnectError:
        return {"type": conn.type, "url": url, "reachable": False,
                "authenticated": False, "details": "Connection refused"}
    except httpx.TimeoutException:
        return {"type": conn.type, "url": url, "reachable": False,
                "authenticated": False, "details": "Timeout (10s)"}
    except Exception as e:
        return {"type": conn.type, "url": url, "reachable": False,
                "authenticated": False, "details": str(e)}


@router.post("/setup/save")
async def save_setup_settings(
    payload: SetupSettings,
    user: TokenPayload = Depends(get_current_user),
):
    """Save settings during onboarding. Admin only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")

    store = get_settings_store()
    from app.config import settings as cfg

    saved = []
    for key, value in payload.settings.items():
        if key in SAVEABLE_FIELDS:
            store.set(key, value)
            if hasattr(cfg, key):
                object.__setattr__(cfg, key, value)
            saved.append(key)

    return {"saved": saved, "count": len(saved)}


@router.post("/setup/complete")
async def complete_setup(user: TokenPayload = Depends(get_current_user)):
    """Mark onboarding as complete. Admin only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")

    store = get_settings_store()
    store.set("onboarding_complete", True)
    return {"complete": True}
