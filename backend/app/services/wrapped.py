"""Plex Wrapped — viewing statistics and insights aggregation.

Uses raw Tautulli history records directly (not WatchEvent) to
access title, year, thumb, section_id and other display fields.
No Seerr enrichment needed — all data comes from Tautulli/Plex.
"""

import logging
from collections import Counter
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Section ID → genre family mapping (matches taste_profiler)
_SECTION_GENRES = {
    "14": "Movies", "20": "Kids Movies",
    "2": "TV", "7": "Kids TV",
    "10": "Anime", "15": "Anime", "17": "Anime",
}


async def build_wrapped(tautulli, user_id: str, username: str, year: int = None) -> dict:
    """Build comprehensive viewing stats from raw Tautulli history.

    Args:
        tautulli: TautulliClient instance
        user_id: Tautulli numeric user_id
        username: Display username
        year: Optional year filter (None = current year)
    """
    now = datetime.now(timezone.utc)
    target_year = year or now.year

    # Fetch history per-section so we know which library each item belongs to
    # Section mapping from config
    sections = {
        "14": "Movies", "20": "Kids Movies",
        "2": "TV Shows", "7": "Kids TV",
        "10": "Anime", "15": "Anime", "17": "Anime",
    }

    filtered = []
    for sid, section_name in sections.items():
        try:
            raw_data = await tautulli._get("get_history", {
                "user_id": user_id,
                "section_id": sid,
                "length": 5000,
            })
            records = raw_data.get("data", []) if isinstance(raw_data, dict) else []
            for r in records:
                started = r.get("started")
                if started:
                    try:
                        dt = datetime.fromtimestamp(int(started), tz=timezone.utc)
                        if dt.year == target_year:
                            r["_dt"] = dt
                            r["_section"] = section_name
                            r["_section_id"] = sid
                            filtered.append(r)
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            logger.warning(f"Failed to fetch history for section {sid}: {e}")

    if not filtered:
        return {"empty": True, "year": target_year, "username": username}

    # ── Basic stats ──────────────────────────────────────────────
    total_duration_s = sum(int(r.get("duration", 0)) for r in filtered)
    total_hours = round(total_duration_s / 3600, 1)

    movies = [r for r in filtered if r.get("media_type") == "movie"]
    episodes = [r for r in filtered if r.get("media_type") == "episode"]

    unique_movies = len(set(r.get("rating_key") for r in movies))
    # Group episodes by show (grandparent_rating_key)
    unique_shows = len(set(r.get("grandparent_rating_key") or r.get("rating_key") for r in episodes))

    avg_completion = round(
        sum(float(r.get("percent_complete", 0)) for r in filtered) / len(filtered), 1
    )

    # ── Hourly distribution ──────────────────────────────────────
    hour_counts = [0] * 24
    for r in filtered:
        hour_counts[r["_dt"].hour] += 1

    peak_hour = hour_counts.index(max(hour_counts)) if any(hour_counts) else 20

    # ── Day of week ──────────────────────────────────────────────
    dow_counts = [0] * 7
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in filtered:
        dow_counts[r["_dt"].weekday()] += 1

    peak_day = dow_names[dow_counts.index(max(dow_counts))] if any(dow_counts) else "Sat"

    # ── Monthly activity ─────────────────────────────────────────
    month_counts = [0] * 12
    month_hours = [0.0] * 12
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for r in filtered:
        m = r["_dt"].month - 1
        month_counts[m] += 1
        month_hours[m] += int(r.get("duration", 0)) / 3600
    month_hours = [round(x, 1) for x in month_hours]

    # ── Content type breakdown from library sections ────────────
    section_counter = Counter()
    for r in filtered:
        section_counter[r.get("_section", "Other")] += 1

    genre_data = [{"genre": g, "count": c} for g, c in section_counter.most_common(12)]

    # ── Top watched movies ───────────────────────────────────────
    movie_counter = Counter()
    movie_info = {}
    for r in movies:
        key = r.get("rating_key")
        movie_counter[key] += 1
        if key not in movie_info:
            movie_info[key] = {
                "title": r.get("title", "Unknown"),
                "year": r.get("year"),
                "thumb": r.get("thumb", ""),
            }

    top_movies = []
    for key, count in movie_counter.most_common(10):
        info = movie_info.get(key, {})
        top_movies.append({
            "title": info.get("title", "Unknown"),
            "year": info.get("year"),
            "thumb": info.get("thumb", ""),
            "plays": count,
        })

    # ── Top watched shows ────────────────────────────────────────
    show_counter = Counter()
    show_info = {}
    for r in episodes:
        key = r.get("grandparent_rating_key") or r.get("rating_key")
        show_counter[key] += 1
        if key not in show_info:
            show_info[key] = {
                "title": r.get("grandparent_title") or r.get("title", "Unknown"),
                "year": r.get("year"),
                "thumb": r.get("grandparent_thumb") or r.get("thumb", ""),
            }

    top_shows = []
    for key, count in show_counter.most_common(10):
        info = show_info.get(key, {})
        top_shows.append({
            "title": info.get("title", "Unknown"),
            "year": info.get("year"),
            "thumb": info.get("thumb", ""),
            "plays": count,
        })

    # ── Binge sessions (3+ episodes of same show within 6h) ─────
    eps_sorted = sorted(
        [r for r in episodes if r.get("_dt")],
        key=lambda r: r["_dt"]
    )
    binge_count = 0
    window = []
    for ep in eps_sorted:
        show_key = ep.get("grandparent_rating_key") or ep.get("rating_key")
        # Trim window to 6h
        window = [(w, wk) for w, wk in window
                  if (ep["_dt"] - w["_dt"]).total_seconds() < 21600]
        window.append((ep, show_key))
        # Count same-show entries in window
        same_show = [wk for _, wk in window if wk == show_key]
        if len(same_show) >= 3:
            binge_count += 1
            window = [(ep, show_key)]

    # ── Longest streak ───────────────────────────────────────────
    watch_dates = sorted(set(r["_dt"].date() for r in filtered))
    longest_streak = 1
    current_streak = 1
    for i in range(1, len(watch_dates)):
        if (watch_dates[i] - watch_dates[i - 1]).days == 1:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 1
    longest_streak = max(longest_streak, current_streak) if watch_dates else 0

    # ── Platform breakdown ───────────────────────────────────────
    platform_counter = Counter()
    for r in filtered:
        platform_counter[r.get("platform", "Unknown")] += 1
    platform_data = [{"platform": p, "count": c} for p, c in platform_counter.most_common(6)]

    return {
        "empty": False,
        "year": target_year,
        "username": username,
        "summary": {
            "total_hours": total_hours,
            "total_plays": len(filtered),
            "movies_watched": unique_movies,
            "shows_watched": unique_shows,
            "episodes_watched": len(episodes),
            "avg_completion": avg_completion,
            "binge_sessions": binge_count,
            "longest_streak_days": longest_streak,
            "feature_films_equivalent": int(round(total_hours / 2, 0)),
            "days_equivalent": round(total_hours / 24, 1),
        },
        "peak": {
            "hour": peak_hour,
            "hour_label": f"{peak_hour:02d}:00",
            "day": peak_day,
        },
        "charts": {
            "hourly": [{"hour": f"{i:02d}:00", "plays": hour_counts[i]} for i in range(24)],
            "daily": [{"day": dow_names[i], "plays": dow_counts[i]} for i in range(7)],
            "monthly": [{"month": month_names[i], "plays": month_counts[i], "hours": month_hours[i]} for i in range(12)],
            "genres": genre_data,
            "platforms": platform_data,
        },
        "top_movies": top_movies,
        "top_shows": top_shows,
    }
