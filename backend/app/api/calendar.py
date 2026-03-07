"""Coming Soon / Release Calendar — upcoming movies and TV from TMDB + Radarr/Sonarr."""

import logging
from datetime import datetime
from fastapi import APIRouter, Query
from app.services.factory import get_stack
from app.services.cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_date(raw: str | None) -> str | None:
    """Extract YYYY-MM-DD from various date formats (ISO 8601, date-only, etc.)."""
    if not raw:
        return None
    try:
        # Handle ISO 8601 with time/timezone
        if "T" in raw:
            return raw.split("T")[0]
        # Already YYYY-MM-DD
        datetime.strptime(raw, "%Y-%m-%d")
        return raw
    except (ValueError, AttributeError):
        return None


def _merge_and_dedupe(tmdb_items: list[dict], arr_items: list[dict]) -> list[dict]:
    """Merge TMDB discover results with Radarr/Sonarr calendar, deduplicating by tmdb_id.

    Radarr/Sonarr items win (they carry monitored status). TMDB fills the gaps.
    """
    seen = {}
    # Arr items first (higher priority — they're monitored)
    for item in arr_items:
        key = (item.get("tmdb_id"), item.get("media_type"))
        if key[0] and key not in seen:
            seen[key] = item

    # TMDB items fill gaps
    for item in tmdb_items:
        key = (item.get("tmdb_id"), item.get("media_type"))
        if key[0] and key not in seen:
            seen[key] = item

    # Sort by release date
    result = sorted(
        seen.values(),
        key=lambda x: x.get("release_date") or "9999-12-31",
    )
    return result


@router.get("/calendar")
async def get_calendar(
    days: int = Query(90, ge=7, le=365, description="Days ahead to look"),
    media_type: str = Query("all", regex="^(all|movie|tv)$"),
    source: str = Query("all", regex="^(all|tmdb|monitored)$"),
    page: int = Query(1, ge=1, le=20),
):
    """Coming Soon calendar — combines TMDB upcoming with Radarr/Sonarr monitored items."""
    cache = get_cache()
    cache_key = f"calendar:{days}:{media_type}:{source}:{page}"
    cached = cache.get_generic(cache_key)
    if cached:
        return cached

    stack = get_stack()
    tmdb_movies, tmdb_tv, arr_movies, arr_tv = [], [], [], []

    # ── Fetch TMDB upcoming ──────────────────────────────────
    if stack.tmdb and source in ("all", "tmdb"):
        try:
            if media_type in ("all", "movie"):
                results, _ = await stack.tmdb.discover_upcoming("movie", days, page)
                tmdb_movies = [
                    {
                        "tmdb_id": r.tmdb_id,
                        "title": r.title,
                        "release_date": r.release_date,
                        "media_type": "movie",
                        "poster": f"https://image.tmdb.org/t/p/w300{r.poster_path}" if r.poster_path else None,
                        "overview": r.overview or "",
                        "vote_average": r.vote_average,
                        "popularity": r.popularity,
                        "source": "tmdb",
                        "monitored": False,
                    }
                    for r in results
                    if r.tmdb_id
                ]
            if media_type in ("all", "tv"):
                results, _ = await stack.tmdb.discover_upcoming("tv", days, page)
                tmdb_tv = [
                    {
                        "tmdb_id": r.tmdb_id,
                        "title": r.title,
                        "release_date": r.release_date,
                        "media_type": "tv",
                        "poster": f"https://image.tmdb.org/t/p/w300{r.poster_path}" if r.poster_path else None,
                        "overview": r.overview or "",
                        "vote_average": r.vote_average,
                        "popularity": r.popularity,
                        "source": "tmdb",
                        "monitored": False,
                    }
                    for r in results
                    if r.tmdb_id
                ]
        except Exception as e:
            logger.warning("TMDB upcoming fetch failed: %s", e)

    # ── Fetch Radarr/Sonarr calendars ────────────────────────
    if source in ("all", "monitored"):
        try:
            if media_type in ("all", "movie"):
                arr_movies = await stack.radarr.get_calendar(days)
        except Exception as e:
            logger.debug("Radarr calendar: %s", e)

        # Sonarr — get all instances from registry
        if media_type in ("all", "tv"):
            for name in ("sonarr_tv", "sonarr_anime"):
                try:
                    client = stack.registry.get(name)
                    if client and hasattr(client, "get_calendar"):
                        eps = await client.get_calendar(days)
                        arr_tv.extend(eps)
                except Exception as e:
                    logger.debug("Sonarr %s calendar: %s", name, e)

    # ── Normalize dates ──────────────────────────────────────
    for item in tmdb_movies + tmdb_tv + arr_movies + arr_tv:
        item["release_date"] = _normalize_date(item.get("release_date"))

    # ── Merge + dedupe ───────────────────────────────────────
    movies = _merge_and_dedupe(tmdb_movies, arr_movies)
    tv = _merge_and_dedupe(tmdb_tv, arr_tv)
    combined = sorted(
        movies + tv,
        key=lambda x: x.get("release_date") or "9999-12-31",
    )

    # ── Group by week ────────────────────────────────────────
    weeks = {}
    for item in combined:
        rd = item.get("release_date")
        if rd:
            try:
                dt = datetime.strptime(rd, "%Y-%m-%d")
                # Week starts Monday
                week_start = dt - __import__("datetime").timedelta(days=dt.weekday())
                week_key = week_start.strftime("%Y-%m-%d")
            except ValueError:
                week_key = "unknown"
        else:
            week_key = "unknown"
        weeks.setdefault(week_key, []).append(item)

    result = {
        "total": len(combined),
        "days_ahead": days,
        "media_type": media_type,
        "source": source,
        "weeks": weeks,
        "items": combined,
    }
    cache.set_generic(cache_key, result, ttl=cache.CALENDAR_TTL)
    return result
