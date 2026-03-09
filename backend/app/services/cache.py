"""Recommendation cache — in-memory TTL cache for computed results.

Caches:
  - Recommendation results per (user, mode, domain) — short TTL (15 min)
  - Library candidates (Radarr/Sonarr) — medium TTL (30 min)
  - TMDB ID resolutions (rating_key → tmdb_id) — long TTL (24 hours)
"""

import logging
import time

# Module-level TTL constants for cross-module use
DATA_LAYER_TTL = 1800  # 30 min — Radarr library IDs, watched sets, collection results
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Single cached value with TTL."""
    value: Any
    created_at: float
    ttl_seconds: float

    @property
    def is_fresh(self) -> bool:
        return (time.time() - self.created_at) < self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class RecommendationCache:
    """Multi-tier in-memory cache for the recommendation pipeline."""

    # TTL defaults (seconds)
    RECS_TTL = 900          # 15 min for recommendation results
    LIBRARY_TTL = 1800      # 30 min for Radarr/Sonarr library data
    TMDB_TTL = 86400         # 24 hours for rating_key → tmdb_id mappings
    PROFILE_TTL = 7200       # 2 hours for user taste profiles

    def __init__(self):
        self._recs: dict[str, CacheEntry] = {}
        self._library: dict[str, CacheEntry] = {}
        self._tmdb_ids: dict[str, CacheEntry] = {}
        self._profiles: dict[str, CacheEntry] = {}
        self._generic: dict[str, CacheEntry] = {}
        self._stats = {"hits": 0, "misses": 0}
        self._user_refresh_at: dict[str, float] = {}  # username → epoch
        self._last_refresh_ms: int = 0
        self._last_refresh_at: str = ""
        self._step_durations: dict[str, int] = {}

    # ── Recommendation results ───────────────────────────────────

    def get_recs(self, username: str, mode: str, domain: str) -> Optional[list]:
        key = f"{username}:{mode}:{domain}"
        entry = self._recs.get(key)
        if entry and entry.is_fresh:
            self._stats["hits"] += 1
            logger.debug(f"Cache HIT recs:{key} (age={entry.age_seconds:.0f}s)")
            return entry.value
        self._stats["misses"] += 1
        return None

    def set_recs(self, username: str, mode: str, domain: str, recs: list):
        key = f"{username}:{mode}:{domain}"
        self._recs[key] = CacheEntry(value=recs, created_at=time.time(), ttl_seconds=self.RECS_TTL)
        logger.debug(f"Cache SET recs:{key} ({len(recs)} items, TTL={self.RECS_TTL}s)")

    # ── Library candidates ───────────────────────────────────────

    def get_library(self, domain: str) -> Optional[list]:
        entry = self._library.get(domain)
        if entry and entry.is_fresh:
            return entry.value
        return None

    def set_library(self, domain: str, candidates: list):
        self._library[domain] = CacheEntry(value=candidates, created_at=time.time(), ttl_seconds=self.LIBRARY_TTL)
        logger.debug(f"Cache SET library:{domain} ({len(candidates)} items)")

    # ── TMDB ID resolution ───────────────────────────────────────

    def get_tmdb_id(self, rating_key: str) -> Optional[int]:
        entry = self._tmdb_ids.get(rating_key)
        if entry and entry.is_fresh:
            return entry.value
        return None

    def set_tmdb_id(self, rating_key: str, tmdb_id: int | None):
        self._tmdb_ids[rating_key] = CacheEntry(value=tmdb_id, created_at=time.time(), ttl_seconds=self.TMDB_TTL)

    # ── Taste profiles ───────────────────────────────────────────

    def get_profile(self, username: str, domain: str):
        key = f"{username}:{domain}"
        entry = self._profiles.get(key)
        if entry and entry.is_fresh:
            return entry.value
        return None

    def set_profile(self, username: str, domain: str, profile):
        key = f"{username}:{domain}"
        self._profiles[key] = CacheEntry(value=profile, created_at=time.time(), ttl_seconds=self.PROFILE_TTL)

    # ── Collections ───────────────────────────────────────────────

    COLLECTIONS_TTL = 21600  # 6 hours for collection scan results

    def get_collections(self, username: str) -> Optional[list]:
        key = f"coll:{username}"
        entry = self._recs.get(key)  # reuse _recs store
        if entry and entry.is_fresh:
            self._stats["hits"] += 1
            return entry.value
        self._stats["misses"] += 1
        return None

    def set_collections(self, username: str, data: list):
        key = f"coll:{username}"
        self._recs[key] = CacheEntry(value=data, created_at=time.time(), ttl_seconds=self.COLLECTIONS_TTL)
        logger.debug(f"Cache SET collections:{username} ({len(data)} collections)")

    # ── Generic TTL cache ─────────────────────────────────────────
    # Use for any endpoint that needs simple key → value caching

    CALENDAR_TTL = 300       # 5 min for calendar data
    NOTIFICATIONS_TTL = 60   # 1 min for notification aggregation
    GENERIC_TTL = 300        # 5 min default

    def get_generic(self, key: str) -> Optional[Any]:
        entry = self._generic.get(key)
        if entry and entry.is_fresh:
            self._stats["hits"] += 1
            logger.debug(f"Cache HIT generic:{key} (age={entry.age_seconds:.0f}s)")
            return entry.value
        self._stats["misses"] += 1
        return None

    def set_generic(self, key: str, value: Any, ttl: float = None):
        self._generic[key] = CacheEntry(
            value=value, created_at=time.time(),
            ttl_seconds=ttl or self.GENERIC_TTL,
        )
        logger.debug(f"Cache SET generic:{key} (TTL={ttl or self.GENERIC_TTL}s)")

    def invalidate_generic(self, prefix: str = ""):
        """Invalidate generic cache entries, optionally filtered by key prefix."""
        if prefix:
            keys = [k for k in self._generic if k.startswith(prefix)]
            for k in keys:
                del self._generic[k]
            logger.debug(f"Invalidated {len(keys)} generic entries with prefix={prefix}")
        else:
            self._generic.clear()
            logger.debug("Cleared all generic cache entries")

    # ── Maintenance ──────────────────────────────────────────────

    def invalidate_user(self, username: str):
        """Invalidate all caches for a specific user (e.g., after new watch event)."""
        removed = 0
        for cache in (self._recs, self._profiles):
            keys = [k for k in cache if k.startswith(f"{username}:") or k == f"coll:{username}"]
            for k in keys:
                del cache[k]
                removed += 1
        logger.info(f"Invalidated {removed} cache entries for user={username}")

    def invalidate_all(self):
        """Full cache clear."""
        for cache in (self._recs, self._library, self._profiles, self._generic):
            cache.clear()
        # Keep TMDB IDs — those don't change
        logger.info("Cache fully invalidated (TMDB IDs retained)")

    def get_stats(self) -> dict:
        """Cache statistics for health/debug endpoint."""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{(self._stats['hits'] / total * 100):.1f}%" if total > 0 else "N/A",
            "cached_recs": len(self._recs),
            "cached_library": len(self._library),
            "cached_tmdb_ids": len(self._tmdb_ids),
            "cached_profiles": len(self._profiles),
            "fresh_recs": sum(1 for e in self._recs.values() if e.is_fresh),
            "cached_generic": len(self._generic),
        }

    # ── Refresh tracking ─────────────────────────────────────────

    def set_last_refresh(self, duration_ms: int):
        """Record completion of a full refresh cycle."""
        import datetime
        self._last_refresh_ms = duration_ms
        self._last_refresh_at = datetime.datetime.now().isoformat()

    def get_last_refresh_duration(self) -> int:
        return self._last_refresh_ms

    def get_last_refresh_time(self) -> str:
        return self._last_refresh_at

    def set_step_duration(self, step_key: str, duration_ms: int):
        self._step_durations[step_key] = duration_ms

    def get_step_durations(self) -> dict[str, int]:
        return dict(self._step_durations)

    # ── Per-user refresh tracking ────────────────────────────────

    def set_user_refresh(self, username: str):
        """Record that a user's caches were refreshed now."""
        self._user_refresh_at[username] = time.time()

    def get_user_refresh_at(self, username: str) -> Optional[float]:
        """Get epoch timestamp of last refresh for a user."""
        return self._user_refresh_at.get(username)

    def get_all_user_refreshes(self) -> dict[str, float]:
        """Get all per-user refresh timestamps."""
        return dict(self._user_refresh_at)

    def get_recs_age(self, username: str, mode: str, domain: str) -> float | None:
        """Return age in seconds of cached recs, or None if not cached."""
        key = f"{username}:{mode}:{domain}"
        entry = self._recs.get(key)
        if entry and entry.is_fresh:
            return entry.age_seconds
        return None

    def get_all_recs_ages(self, username: str, domain: str = "all") -> dict[str, float]:
        """Return ages for all cached modes for a user."""
        ages = {}
        for mode in ("tonight", "grab", "rediscover", "trending"):
            age = self.get_recs_age(username, mode, domain)
            if age is not None:
                ages[mode] = round(age, 1)
        return ages

    def cleanup_stale(self):
        """Remove expired entries (call periodically)."""
        removed = 0
        for cache in (self._recs, self._library, self._tmdb_ids, self._profiles, self._generic):
            stale = [k for k, v in cache.items() if not v.is_fresh]
            for k in stale:
                del cache[k]
                removed += len(stale)
        if removed:
            logger.debug(f"Cleaned {removed} stale cache entries")


# ── Singleton instance ───────────────────────────────────────────
_cache: Optional[RecommendationCache] = None


def get_cache() -> RecommendationCache:
    global _cache
    if _cache is None:
        _cache = RecommendationCache()
    return _cache
