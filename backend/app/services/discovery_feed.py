"""Discovery Feed — generates themed "Your Weekly Mix" sections.

Three sections per user, cached for 24 hours:
  1. Fresh Picks — recently added library items matching taste
  2. Hidden Gems — high-rated but underwatched library items
  3. Because You Liked [X] — similar to a recent favorite
"""

import logging
import random
from dataclasses import asdict
from typing import Optional

from app.services.cache import get_cache
from app.services.rec_library import get_library_candidates
from app.services.rec_types import Recommendation
from app.api.rec_helpers import img_url


async def _get_library_candidates(stack):
    """Get library candidates from cache or rebuild on the fly."""
    cache = get_cache()
    candidates = cache.get_library("all")
    if candidates:
        return candidates
    # Cache expired — rebuild from Radarr/Sonarr
    try:
        from app.services.rec_library import get_library_candidates
        candidates = await get_library_candidates(
            stack.radarr if stack.registry.get_by_type("radarr") else None,
            stack.sonarr_tv if (stack.registry.get("sonarr_tv") or stack.registry.get_default_for("tv")) else None,
            stack.sonarr_anime if stack.registry.get("sonarr_anime") else None,
            "all",
        )
        if candidates:
            cache.set_library("all", candidates)
        return candidates or []
    except Exception as e:
        logger.warning(f"Library rebuild for feed failed: {e}")
        return []

logger = logging.getLogger(__name__)

FEED_CACHE_TTL = 86400  # 24 hours
SECTION_SIZE = 8


async def _resolve_user_id(stack, username: str) -> str | None:
    """Resolve username → Tautulli numeric user_id."""
    try:
        users = await stack.tautulli.get_users()
        for u in users:
            uname = u.get("username", "") or u.get("friendly_name", "")
            if uname == username:
                return str(u.get("user_id", ""))
    except Exception as e:
        logger.warning(f"Could not resolve username {username}: {e}")
    return None


async def generate_feed(username: str) -> dict:
    """Generate or return cached discovery feed for a user."""
    cache = get_cache()
    cache_key = f"feed:{username}"
    cached = cache.get_generic(cache_key)
    if cached is not None:
        return cached

    from app.services.factory import get_stack
    stack = get_stack()

    sections = []

    # Section 1: Fresh Picks
    fresh = await _fresh_picks(stack, username)
    if fresh:
        sections.append(fresh)

    # Section 2: Hidden Gems
    gems = await _hidden_gems(stack, username)
    if gems:
        sections.append(gems)

    # Section 3: Because You Liked [X]
    because = await _because_you_liked(stack, username)
    if because:
        sections.append(because)

    feed = {"sections": sections, "username": username}
    cache.set_generic(cache_key, feed, ttl=FEED_CACHE_TTL)
    return feed


async def _fresh_picks(stack, username: str) -> Optional[dict]:
    """Recently added library items that match user taste profile."""
    try:
        cache = get_cache()
        profile = cache.get_profile(username, "all")
        if not profile:
            return None

        candidates = await _get_library_candidates(stack)
        if not candidates:
            return None

        # Get user's top genres from profile
        top_genres = set()
        if hasattr(profile, "top_genres") and profile.genres:
            top_genres = {g.genre for g in profile.top_genres(8)}

        # Get watched set to filter
        watched_ids = set()
        if stack.tautulli:
            tautulli_id = await _resolve_user_id(stack, username)
            if tautulli_id:
                history = await stack.tautulli.get_history(user_id=tautulli_id, limit=500)
                watched_ids = {h.tmdb_id for h in history if h.tmdb_id}

        # Sort by added_at descending (recently added first), exclude watched
        recent = sorted(
            [c for c in candidates if c.get("added_at") and c.get("tmdb_id") not in watched_ids],
            key=lambda c: c["added_at"],
            reverse=True,
        )[:100]  # top 100 most recent unwatched

        # Score by genre overlap with taste profile, fall back to rating
        if top_genres:
            scored = []
            for item in recent:
                item_genres = set(item.get("genres") or [])
                overlap = len(item_genres & top_genres)
                if overlap > 0:
                    scored.append((overlap, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            picks = [_to_feed_item(item) for _, item in scored[:SECTION_SIZE]]
        else:
            # No genre data — fall back to highest rated recent additions
            recent.sort(key=lambda c: (c.get("vote_average") or 0), reverse=True)
            picks = [_to_feed_item(item) for item in recent[:SECTION_SIZE]]

        if not picks:
            return None

        return {
            "id": "fresh_picks",
            "title": "Fresh Picks",
            "subtitle": "Recently added, matched to your taste",
            "icon": "sparkles",
            "items": picks,
        }
    except Exception as e:
        logger.warning(f"Fresh picks generation failed for {username}: {e}")
        return None


async def _hidden_gems(stack, username: str) -> Optional[dict]:
    """High-rated library items that are underwatched."""
    try:
        cache = get_cache()
        candidates = await _get_library_candidates(stack)
        if not candidates:
            return None

        # Get user's watched set from Tautulli
        watched_ids = set()
        if stack.tautulli:
            tautulli_id = await _resolve_user_id(stack, username)
            if tautulli_id:
                history = await stack.tautulli.get_history(
                    user_id=tautulli_id, limit=500
                )
                watched_ids = {h.tmdb_id for h in history if h.tmdb_id}

        # Filter: high rating, not watched, in library
        gems = [
            c for c in candidates
            if (c.get("vote_average") or 0) >= 7.0
            and c.get("tmdb_id") not in watched_ids
            and c.get("in_library")
        ]

        # Sort by rating, take a random sample from top tier
        gems.sort(key=lambda c: (c.get("vote_average") or 0), reverse=True)
        top_tier = gems[:30]  # top 30 highest rated unwatched
        if len(top_tier) > SECTION_SIZE:
            selected = random.sample(top_tier, SECTION_SIZE)
        else:
            selected = top_tier[:SECTION_SIZE]

        picks = [_to_feed_item(item) for item in selected]
        if not picks:
            return None

        return {
            "id": "hidden_gems",
            "title": "Hidden Gems",
            "subtitle": "Highly rated in your library, waiting to be discovered",
            "icon": "gem",
            "items": picks,
        }
    except Exception as e:
        logger.warning(f"Hidden gems generation failed for {username}: {e}")
        return None


async def _because_you_liked(stack, username: str) -> Optional[dict]:
    """Find a recent favorite and recommend similar titles."""
    try:
        if not stack.tautulli or not stack.tmdb:
            return None

        tautulli_id = await _resolve_user_id(stack, username)
        if not tautulli_id:
            return None

        history = await stack.tautulli.get_history(
            user_id=tautulli_id, limit=50
        )

        if not history:
            return None

        # Find recent well-rated movie/show (resolve tmdb_id if needed)
        anchor = None
        high_completion = [h for h in history if h.completion_pct and h.completion_pct > 75][:20]
        for h in high_completion:
            tmdb_id = h.tmdb_id
            if not tmdb_id:
                try:
                    tmdb_id = await stack.tautulli.resolve_tmdb_id(h.item_key, h.media_type or "movie")
                except Exception:
                    continue
            if not tmdb_id:
                continue
            try:
                mt = h.media_type if h.media_type in ("movie", "tv") else "movie"
                detail = await stack.tmdb.get_detail(tmdb_id, mt)
                if detail and detail.get("vote_average", 0) >= 6.5:
                    anchor = {
                        "tmdb_id": tmdb_id,
                        "title": detail.get("title", "Unknown"),
                        "media_type": mt,
                    }
                    break
            except Exception:
                continue

        if not anchor:
            return None

        # Get similar titles
        similar = await stack.tmdb.get_similar(anchor["tmdb_id"], anchor["media_type"])
        picks = [
            _to_feed_item({
                "tmdb_id": s.tmdb_id,
                "title": s.title,
                "year": s.year,
                "media_type": s.media_type,
                "poster_path": s.poster_path,
                "vote_average": s.vote_average,
                "overview": s.overview,
                "genres": s.genres if hasattr(s, "genres") else [],
                "in_library": False,
            })
            for s in similar[:SECTION_SIZE]
        ]

        if not picks:
            return None

        return {
            "id": "because_you_liked",
            "title": f"Because You Liked {anchor['title']}",
            "subtitle": "Similar titles you might enjoy",
            "icon": "heart",
            "anchor_tmdb_id": anchor["tmdb_id"],
            "items": picks,
        }
    except Exception as e:
        logger.warning(f"Because-you-liked generation failed for {username}: {e}")
        return None


def _to_feed_item(candidate: dict) -> dict:
    """Normalize a candidate/result into a feed item shape."""
    return {
        "tmdb_id": candidate.get("tmdb_id"),
        "title": candidate.get("title", "Unknown"),
        "year": candidate.get("year"),
        "media_type": candidate.get("media_type", "movie"),
        "poster_path": candidate.get("poster_path"),
        "poster_url": img_url(candidate.get("poster_path"), "w342"),
        "vote_average": candidate.get("vote_average"),
        "overview": candidate.get("overview", ""),
        "genres": candidate.get("genres", []),
        "in_library": candidate.get("in_library", False),
    }
