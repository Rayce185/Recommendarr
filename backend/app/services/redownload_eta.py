"""Re-download ETA — heuristic baseline + live indexer probe.

Heuristic tier (instant) uses TMDB metadata for quick estimates.
Live probe (on-demand) queries Radarr/Sonarr search API for real data.
"""

import logging
from typing import Optional

from app.services.vitality_scoring import estimate_redownload_tier

logger = logging.getLogger(__name__)

# Tier descriptions for UI display
TIER_DESCRIPTIONS = {
    "instant": "Very popular — re-download within minutes",
    "hours": "Well-known — expect 1-6 hours",
    "days": "Moderate availability — may take 1-3 days",
    "weeks": "Limited availability — could take 1-2 weeks",
    "rare": "Rare release — may be difficult to find",
}


def get_heuristic_eta(
    popularity: Optional[float] = None,
    year: Optional[int] = None,
    original_language: Optional[str] = None,
) -> dict:
    """Return heuristic ETA tier with description. Instant, no API calls."""
    tier = estimate_redownload_tier(popularity, year, original_language)
    return {
        "tier": tier,
        "description": TIER_DESCRIPTIONS.get(tier, "Unknown"),
        "source": "heuristic",
    }


async def probe_indexer_availability(
    tmdb_id: int, media_type: str,
) -> dict:
    """Live probe: query Radarr/Sonarr search API for actual indexer results.

    This makes real API calls to indexers — use sparingly (on user click).
    Returns result count, best available quality, and updated tier.
    """
    import httpx
    from app.services.factory import get_stack

    stack = get_stack()
    result = {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "source": "live_probe",
        "results_found": 0,
        "best_quality": None,
        "tier": "rare",
        "description": TIER_DESCRIPTIONS["rare"],
        "error": None,
    }

    try:
        if media_type == "movie":
            client = stack.registry.get_default_for("movie")
            if not client:
                result["error"] = "No Radarr instance configured"
                return result

            # Radarr release search by TMDB ID
            async with httpx.AsyncClient(timeout=60.0) as http:
                # First check if movie exists in Radarr
                resp = await http.get(
                    f"{client.url}/api/v3/movie",
                    headers=client.headers,
                    params={"tmdbId": tmdb_id},
                )
                if resp.status_code != 200:
                    result["error"] = f"Radarr lookup failed: {resp.status_code}"
                    return result

                movies = resp.json()
                if not movies:
                    # Try lookup for re-add scenario
                    lookup = await client.lookup_movie(tmdb_id)
                    if lookup:
                        result["results_found"] = 1
                        result["tier"] = "hours"
                        result["description"] = "Found in indexers — can be re-added"
                    return result

                movie_id = movies[0]["id"] if isinstance(movies, list) else movies.get("id")
                if not movie_id:
                    return result

                # Search for releases
                resp = await http.get(
                    f"{client.url}/api/v3/release",
                    headers=client.headers,
                    params={"movieId": movie_id},
                    timeout=90.0,
                )
                if resp.status_code == 200:
                    releases = resp.json()
                    result["results_found"] = len(releases)
                    if releases:
                        # Find best quality
                        qualities = [
                            r.get("quality", {}).get("quality", {}).get("name", "")
                            for r in releases
                        ]
                        result["best_quality"] = _rank_best_quality(qualities)
                        result["tier"] = _tier_from_results(len(releases))
                        result["description"] = (
                            f"{len(releases)} results found, best: {result['best_quality']}"
                        )

        else:
            # Sonarr series search
            for inst_name, client in stack.registry.get_by_type("sonarr"):
                if not client:
                    continue

                async with httpx.AsyncClient(timeout=60.0) as http:
                    resp = await http.get(
                        f"{client.url}/api/v3/series",
                        headers=client.headers,
                        params={"tmdbId": tmdb_id},
                    )
                    if resp.status_code == 200:
                        series = resp.json()
                        if series:
                            result["results_found"] = len(series)
                            result["tier"] = "hours"
                            result["description"] = "Series found in Sonarr — can be re-monitored"
                            break

    except Exception as e:
        logger.error("Live probe failed for tmdb=%d: %s", tmdb_id, e)
        result["error"] = str(e)

    return result


def _rank_best_quality(qualities: list[str]) -> str:
    """Pick the highest quality from a list of quality names."""
    ranking = [
        "Remux-2160p", "Bluray-2160p", "WEBDL-2160p", "WEBRip-2160p",
        "Remux-1080p", "Bluray-1080p", "WEBDL-1080p", "WEBRip-1080p",
        "Bluray-720p", "WEBDL-720p", "HDTV-1080p", "HDTV-720p",
        "WEBDL-480p", "DVD", "SDTV",
    ]
    for q in ranking:
        for available in qualities:
            if q.lower() in available.lower():
                return q
    return qualities[0] if qualities else "Unknown"


def _tier_from_results(count: int) -> str:
    """Map result count to availability tier."""
    if count >= 20:
        return "instant"
    if count >= 5:
        return "hours"
    if count >= 1:
        return "days"
    return "rare"
