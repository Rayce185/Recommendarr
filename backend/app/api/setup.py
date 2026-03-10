"""Onboarding wizard and setup endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import httpx

from app.services.factory import get_stack

router = APIRouter()


class ConnectionTest(BaseModel):
    type: str          # plex | tautulli | radarr | sonarr | seerr | ollama | tmdb
    url: str
    api_key: Optional[str] = None
    token: Optional[str] = None


@router.get("/setup/status")
async def setup_status():
    """Check which setup steps have been completed by probing real state."""
    stack = get_stack()

    # 1. Server connected — Plex reachable?
    server_connected = False
    if stack.plex:
        try:
            server_connected = await stack.plex.test_connection()
        except Exception:
            pass

    # 2. Integrations configured — key services reachable?
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

    integrations_configured = all(integrations.values())

    # 3. Users synced — user_map populated?
    users_synced = bool(stack.user_map and len(stack.user_map) > 0)

    # 4. First user onboarded — at least one non-admin user exists?
    first_user_onboarded = users_synced and len(stack.user_map) >= 1

    return {
        "server_connected": server_connected,
        "integrations_configured": integrations_configured,
        "integrations_detail": integrations,
        "users_synced": users_synced,
        "user_count": len(stack.user_map) if stack.user_map else 0,
        "first_user_onboarded": first_user_onboarded,
        "complete": all([
            server_connected,
            integrations_configured,
            users_synced,
            first_user_onboarded,
        ]),
    }


@router.post("/setup/integrations/test")
async def test_integration(conn: ConnectionTest):
    """Test connection to any integration (Plex, Radarr, Tautulli, etc.)."""
    url = conn.url.rstrip("/")

    # Build probe URL and headers based on type
    probe_paths = {
        "plex": "/",
        "tautulli": "/api/v2?apikey={key}&cmd=arnold",
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
        probe_url = f"{url}{path}"
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
        return {"type": conn.type, "url": url, "reachable": False, "authenticated": False, "details": "Connection refused"}
    except httpx.TimeoutException:
        return {"type": conn.type, "url": url, "reachable": False, "authenticated": False, "details": "Timeout (10s)"}
    except Exception as e:
        return {"type": conn.type, "url": url, "reachable": False, "authenticated": False, "details": str(e)}
