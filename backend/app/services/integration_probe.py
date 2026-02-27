"""Probe all configured integrations on startup and report status."""

import httpx
from app.config import Settings


async def probe_all(settings: Settings) -> dict:
    """Check reachability of all configured services. Returns status dict."""
    results = {}

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Plex
        if settings.has_plex:
            results["plex"] = await _probe(
                client, f"{settings.plex_url}/identity",
                headers={"X-Plex-Token": settings.plex_token, "Accept": "application/json"},
            )
        else:
            results["plex"] = {"status": "not_configured"}

        # Tautulli
        if settings.has_tautulli:
            results["tautulli"] = await _probe(
                client,
                f"{settings.tautulli_url}/api/v2?apikey={settings.tautulli_api_key}&cmd=arnold",
            )
        else:
            results["tautulli"] = {"status": "not_configured"}

        # Radarr
        if settings.has_radarr:
            results["radarr"] = await _probe(
                client, f"{settings.radarr_url}/api/v3/system/status",
                headers={"X-Api-Key": settings.radarr_api_key},
            )
        else:
            results["radarr"] = {"status": "not_configured"}

        # Sonarr
        if settings.has_sonarr:
            results["sonarr"] = await _probe(
                client, f"{settings.sonarr_url}/api/v3/system/status",
                headers={"X-Api-Key": settings.sonarr_api_key},
            )
        else:
            results["sonarr"] = {"status": "not_configured"}

        # Seerr
        if settings.has_seerr:
            results["seerr"] = await _probe(
                client, f"{settings.seerr_url}/api/v1/status",
                headers={"X-Api-Key": settings.seerr_api_key},
            )
        else:
            results["seerr"] = {"status": "not_configured"}

        # TMDB
        if settings.has_tmdb:
            results["tmdb"] = await _probe(
                client,
                f"https://api.themoviedb.org/3/configuration?api_key={settings.tmdb_api_key}",
            )
        else:
            results["tmdb"] = {"status": "not_configured"}

        # Ollama
        results["ollama"] = await _probe(client, f"{settings.llm_base_url}/api/tags")

        # ChromaDB (v2 API)
        results["chromadb"] = await _probe(client, f"{settings.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections")

    return results


async def _probe(client: httpx.AsyncClient, url: str, headers: dict | None = None) -> dict:
    """Probe a single endpoint."""
    try:
        resp = await client.get(url, headers=headers)
        return {
            "status": "ok" if resp.status_code < 400 else "error",
            "code": resp.status_code,
        }
    except httpx.ConnectError:
        return {"status": "unreachable"}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}
