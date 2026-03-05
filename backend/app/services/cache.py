"""Recommendation cache — in-memory TTL cache for computed results.

Caches:
  - Recommendation results per (user, mode, domain) — short TTL (15 min)
  - Library candidates (Radarr/Sonarr) — medium TTL (30 min)
  - TMDB ID resolutions (rating_key → tmdb_id) — long TTL (24 hours)
"""

import logging
import time
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
        self._stats = {"hits": 0, "misses": 0}
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

    COLLECTIONS_TTL = 3600  # 1 hour for collection scan results

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

    # ── Maintenance ──────────────────────────────────────────────

    def invalidate_user(self, username: str):
        """Invalidate all caches for a specific user (e.g., after new watch event)."""
        removed = 0
        for cache in (self._recs, self._profiles):
            keys = [k for k in cache if k.startswith(f"{username}:")]
            for k in keys:
                del cache[k]
                removed += 1
        logger.info(f"Invalidated {removed} cache entries for user={username}")

    def invalidate_all(self):
        """Full cache clear."""
        for cache in (self._recs, self._library, self._profiles):
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
        for cache in (self._recs, self._library, self._tmdb_ids, self._profiles):
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
