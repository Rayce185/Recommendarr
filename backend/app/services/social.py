"""Social layer — taste overlap, server stats, and friend discovery.

Computes taste similarity between users based on genre affinities,
keyword overlap, and collaborative filtering signals.
"""

import logging
from dataclasses import dataclass
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class TasteOverlap:
    username: str
    friendly_name: str
    thumb: str
    overlap_pct: float  # 0-100
    shared_genres: list[str]
    unique_to_them: list[str]


def compute_genre_overlap(profile_a, profile_b) -> tuple[float, list[str], list[str]]:
    """Compute genre-based taste overlap between two profiles.

    Returns: (overlap_pct, shared_genres, unique_to_b)
    """
    if not profile_a or not profile_b:
        return 0.0, [], []

    genres_a = {g.genre: g.score for g in profile_a.genres if g.score > 0.1}
    genres_b = {g.genre: g.score for g in profile_b.genres if g.score > 0.1}

    if not genres_a or not genres_b:
        return 0.0, [], []

    all_genres = set(genres_a.keys()) | set(genres_b.keys())
    shared = set(genres_a.keys()) & set(genres_b.keys())

    # Cosine similarity on genre vectors
    dot = sum(genres_a.get(g, 0) * genres_b.get(g, 0) for g in all_genres)
    mag_a = sum(v ** 2 for v in genres_a.values()) ** 0.5
    mag_b = sum(v ** 2 for v in genres_b.values()) ** 0.5

    if mag_a == 0 or mag_b == 0:
        return 0.0, [], []

    cosine = dot / (mag_a * mag_b)
    overlap_pct = round(cosine * 100, 1)

    # Top shared genres (sorted by combined score)
    shared_genres = sorted(shared, key=lambda g: genres_a.get(g, 0) + genres_b.get(g, 0), reverse=True)[:5]

    # Genres unique to profile_b (interesting for discovery)
    unique = sorted(
        set(genres_b.keys()) - set(genres_a.keys()),
        key=lambda g: genres_b[g],
        reverse=True
    )[:3]

    return overlap_pct, shared_genres, unique


async def get_taste_overlaps(profiler, tautulli, username: str, domain: str = "all") -> list[TasteOverlap]:
    """Compute taste overlap between a user and all other server users.

    Args:
        profiler: TasteProfiler instance
        tautulli: TautulliClient instance
        username: The reference user
        domain: Content domain filter

    Returns: Sorted list of TasteOverlap objects (highest overlap first)
    """
    # Get all users
    users = await tautulli.get_users()
    user_map = {u["username"]: u for u in users if u.get("username")}

    # Build reference profile
    ref_profile = await profiler.build_profile(username, domain=domain)
    if not ref_profile or not ref_profile.genres:
        return []

    overlaps = []
    for u in users:
        other = u.get("username", "")
        if not other or other == username or not u.get("is_active", 0):
            continue

        try:
            other_profile = await profiler.build_profile(other, domain=domain)
            if not other_profile or not other_profile.genres:
                continue

            pct, shared, unique = compute_genre_overlap(ref_profile, other_profile)

            overlaps.append(TasteOverlap(
                username=other,
                friendly_name=u.get("friendly_name", other),
                thumb=u.get("thumb", ""),
                overlap_pct=pct,
                shared_genres=shared,
                unique_to_them=unique,
            ))
        except Exception as e:
            logger.warning(f"Failed to compute overlap for {other}: {e}")

    overlaps.sort(key=lambda o: o.overlap_pct, reverse=True)
    return overlaps


async def get_server_stats(tautulli) -> dict:
    """Get server-wide viewing stats for the social dashboard."""
    users = await tautulli.get_users()
    active_count = sum(1 for u in users if u.get("is_active"))

    # Get recent activity across all users
    raw = await tautulli._get("get_history", {"length": 100})
    records = raw.get("data", []) if isinstance(raw, dict) else []

    # Most watched titles server-wide (last 100 plays)
    title_counter = Counter()
    for r in records:
        title = r.get("full_title") or r.get("title", "Unknown")
        title_counter[title] += 1

    server_trending = [{"title": t, "plays": c} for t, c in title_counter.most_common(10)]

    # Unique viewers in the last batch
    unique_viewers = len(set(r.get("user") for r in records if r.get("user")))

    return {
        "total_users": len(users),
        "active_users": active_count,
        "recent_unique_viewers": unique_viewers,
        "server_trending": server_trending,
    }
