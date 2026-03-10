"""Health & system status endpoints v2 — live service probing."""

from fastapi import APIRouter
import time
from datetime import datetime, timezone

from app.services.factory import get_stack

router = APIRouter()


async def _timed_probe(client, name):
    """Probe a service and return status + latency in ms."""
    t0 = time.monotonic()
    try:
        ok = await client.test_connection()
        latency_ms = round((time.monotonic() - t0) * 1000)
        return name, {"status": "ok" if ok else "error", "url": client.url, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return name, {"status": "error", "error": str(e), "url": getattr(client, "url", ""), "latency_ms": latency_ms}


@router.get("/health")
async def health_check():
    """Service health — probes all upstream APIs with latency."""
    stack = get_stack()

    service_getters = [
        ("tautulli", lambda: stack.tautulli),
        ("seerr", lambda: stack.seerr),
        ("radarr", lambda: stack.radarr),
        ("sonarr_tv", lambda: stack.sonarr_tv),
        ("sonarr_anime", lambda: stack.sonarr_anime),
    ]

    # Resolve clients safely (some may not be configured)
    probes = []
    for name, getter in service_getters:
        try:
            probes.append((name, getter()))
        except Exception:
            pass  # skip unconfigured services

    # Probe Plex if configured
    if stack.plex:
        probes.append(("plex", stack.plex))

    import asyncio
    results = await asyncio.gather(*[_timed_probe(c, n) for n, c in probes])
    checks = dict(results)

    all_ok = all(c.get("status") == "ok" for c in checks.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "1.0.0",
        "architecture": "api-first",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": checks,
        "users_loaded": len(stack.user_map) if stack.user_map else 0,
    }


@router.get("/stats")
async def system_stats():
    """Library statistics from Radarr/Sonarr."""
    stack = get_stack()

    stats = {}
    try:
        movies = await stack.radarr.get_all_movies()
        stats["movies"] = len(movies)
    except Exception:
        stats["movies"] = "error"

    try:
        tv = await stack.sonarr_tv.get_all_series()
        stats["tv_series"] = len(tv)
    except Exception:
        stats["tv_series"] = "error"

    try:
        anime = await stack.sonarr_anime.get_all_series()
        stats["anime_series"] = len(anime)
    except Exception:
        stats["anime_series"] = "error"

    try:
        users = await stack.tautulli.get_users()
        stats["users"] = len([u for u in users if u.get("username")])
    except Exception:
        stats["users"] = "error"

    return stats




@router.get("/debug/section-map")
async def debug_section_map():
    """Debug: Show section map distribution and sample entries."""
    stack = get_stack()
    if not stack.plex:
        return {"error": "Plex not configured"}

    # Count items per section
    section_counts = {}
    for key, sec_name in stack.plex._section_map.items():
        section_counts[sec_name] = section_counts.get(sec_name, 0) + 1

    # Sample entries per section (first 3)
    section_samples = {}
    for key, sec_name in stack.plex._section_map.items():
        if sec_name not in section_samples:
            section_samples[sec_name] = []
        if len(section_samples[sec_name]) < 3:
            section_samples[sec_name].append(key)

    # Test specific lookups
    test_lookups = {}
    test_ids = [1429, 100565, 67043]  # Attack on Titan, 86, 91 Days
    for tid in test_ids:
        section = stack.plex.get_section_name(tid, "tv")
        test_lookups[f"show:{tid}"] = section

    return {
        "total_items": len(stack.plex._section_map),
        "section_counts": section_counts,
        "section_samples": section_samples,
        "test_lookups": test_lookups,
        "sections": stack.plex.sections,
    }

@router.get("/genres")
async def get_genres():
    """All available genre lists from TMDB via Seerr."""
    stack = get_stack()

    try:
        movie_genres = await stack.seerr.get_movie_genres()
        tv_genres = await stack.seerr.get_tv_genres()
    except Exception as e:
        return {"error": str(e)}

    return {
        "movie_genres": movie_genres,
        "tv_genres": tv_genres,
    }
