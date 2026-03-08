"""Taste Profiler v2 — API-first, Tautulli as source of truth.

Orchestrator that builds taste profiles from Tautulli watch history,
enriched with TMDB metadata. Delegates to:
  - taste_models: dataclasses, constants, library domain mapping, normalization
  - taste_enrichment: TMDB cache + API metadata fetching
  - taste_collaborative: peer similarity and suggestions
"""

import math
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.clients.tautulli import TautulliClient
from app.clients.seerr import SeerrClient
from app.services.taste_models import (
    SIGNAL_WEIGHTS,
    GenreAffinity,
    KeywordAffinity,
    LanguageAffinity,
    PersonnelAffinity,
    TasteProfile,
    DEFAULT_LIBRARY_DOMAINS,
    normalize_taste_vectors,
)
from app.services.taste_enrichment import enrich_items
from app.services.taste_collaborative import (
    get_collaborative_peers,
    get_collaborative_suggestions,
)

logger = logging.getLogger(__name__)

# Re-export models for backward compatibility
__all__ = [
    "TasteProfiler",
    "TasteProfile",
    "GenreAffinity",
    "KeywordAffinity",
    "PersonnelAffinity",
    "SIGNAL_WEIGHTS",
    "DEFAULT_LIBRARY_DOMAINS",
]


class TasteProfiler:
    """Builds taste profiles from Tautulli API + TMDB metadata.

    API-first architecture — Tautulli is the source of truth for watch
    history, TMDB provides metadata enrichment. PostgreSQL stores
    only the computed profile as a refreshable cache.
    """

    def __init__(
        self,
        tautulli: TautulliClient,
        seerr: SeerrClient,
        tmdb=None,
        library_domains: dict[str, str] | None = None,
    ):
        self.tautulli = tautulli
        self.seerr = seerr
        self.tmdb = tmdb
        self.library_domains = library_domains or DEFAULT_LIBRARY_DOMAINS

    async def build_profile(
        self,
        username: str,
        domain: str = "all",
        depth_months: int = 24,
        enrich_keywords: bool = True,
        max_enrich: int = 100,
    ) -> TasteProfile:
        """Build a complete taste profile from Tautulli history.

        Args:
            username: Tautulli username (matches Plex username)
            domain: "movies", "tv", "anime", or "all"
            depth_months: How far back to look in watch history
            enrich_keywords: Whether to fetch TMDB keywords (slower but richer)
            max_enrich: Max titles to enrich with keywords (rate limit control)
        """
        logger.info(f"Building taste profile for {username} (domain={domain}, depth={depth_months}mo)")

        # 1. Resolve username → numeric user_id
        user_id_match = await self._resolve_user_id(username)

        # 2. Pull watch history from Tautulli
        since = datetime.now(timezone.utc) - timedelta(days=depth_months * 30)
        history = await self.tautulli.get_history(user_id=user_id_match, since=since, limit=10000)

        user_events = [
            e for e in history
            if str(e.user_id) == user_id_match
            or str(e.user_id) == username
            or e.user_id == username
        ]
        if not user_events:
            logger.warning(f"No events found for user_id={user_id_match} (username={username})")

        logger.info(f"Found {len(user_events)} watch events for {username}")

        # 3. Group by item (rating_key)
        by_item: dict[str, list] = defaultdict(list)
        for event in user_events:
            by_item[event.item_key].append(event)

        # 4. Resolve TMDB IDs for items that need it
        t0 = time.monotonic()
        items_needing_tmdb = [
            (key, events[0].media_type)
            for key, events in by_item.items()
            if events[0].tmdb_id is None
        ]
        if items_needing_tmdb:
            tmdb_map = await self.tautulli.resolve_tmdb_ids_batch(items_needing_tmdb[:500])
            for key, events in by_item.items():
                if events[0].tmdb_id is None and key in tmdb_map:
                    for e in events:
                        e.tmdb_id = tmdb_map[key]
        logger.info(f"TMDB ID resolution: {time.monotonic()-t0:.1f}s ({len(items_needing_tmdb)} items)")

        # 5. Enrich with TMDB metadata (genres, keywords, cast/crew)
        enrich_cache = {}
        if enrich_keywords:
            enrich_cache = await enrich_items(
                by_item, tmdb_client=self.tmdb, seerr_client=self.seerr,
                max_enrich=max_enrich,
            )

        # 6. Score titles and build vectors
        profile = self._score_and_normalize(by_item, enrich_cache, username, domain)

        logger.info(
            f"Profile built for {username}: {profile.total_watched} titles, "
            f"{len(profile.genres)} genres, {len(profile.keywords)} keywords, "
            f"{len(profile.personnel)} personnel, {len(enrich_cache)} enriched"
        )
        return profile

    async def get_collaborative_peers(self, username: str, limit: int = 5):
        """Delegate to standalone collaborative filtering."""
        return await get_collaborative_peers(self.tautulli, username, limit)

    async def get_collaborative_suggestions(self, username: str, known_item_keys: set[str], limit: int = 20):
        """Delegate to standalone collaborative filtering."""
        return await get_collaborative_suggestions(self.tautulli, username, known_item_keys, limit)

    # ── Private helpers ──────────────────────────────────────────

    async def _resolve_user_id(self, username: str) -> str:
        """Resolve Tautulli username → numeric user_id."""
        try:
            users = await self.tautulli.get_users()
            for u in users:
                uname = u.get("username", "") or u.get("friendly_name", "")
                if uname == username:
                    uid = str(u.get("user_id", ""))
                    logger.info(f"Resolved username '{username}' → user_id '{uid}'")
                    return uid
        except Exception as e:
            logger.warning(f"Could not resolve username: {e}")
        return username

    def _score_and_normalize(
        self,
        by_item: dict[str, list],
        enrich_cache: dict[str, dict],
        username: str,
        domain: str,
    ) -> TasteProfile:
        """Score each title and normalize into 0.0–1.0 vectors."""
        now = datetime.now(timezone.utc)
        genre_scores: dict[str, dict] = defaultdict(
            lambda: {"score": 0.0, "count": 0, "completions": [], "hours": 0.0}
        )
        keyword_scores: dict[str, dict] = defaultdict(
            lambda: {"score": 0.0, "count": 0}
        )
        personnel_scores: dict[str, dict] = defaultdict(
            lambda: {"score": 0.0, "count": 0, "completions": [], "role": ""}
        )
        language_counts: dict[str, int] = defaultdict(int)
        total_watched = 0
        total_hours = 0.0
        completions = []
        rewatch_count = 0

        for item_key, events in by_item.items():
            primary = events[0]

            # Domain filtering
            item_domain = "movies" if primary.media_type == "movie" else "tv"
            if domain != "all" and item_domain != domain:
                continue

            # Per-title signals
            watch_count = len(events)
            best_completion = max(e.completion_pct for e in events)
            total_duration = sum(e.duration_seconds for e in events)
            most_recent = max((e.started_at for e in events if e.started_at), default=now)
            if most_recent.tzinfo is None:
                most_recent = most_recent.replace(tzinfo=timezone.utc)

            # Completion signal
            if best_completion >= 85:
                comp_signal = SIGNAL_WEIGHTS["completion_full"]
            elif best_completion >= 40:
                comp_signal = SIGNAL_WEIGHTS["completion_good"]
            elif best_completion < 20 and watch_count == 1:
                comp_signal = SIGNAL_WEIGHTS["completion_abandoned"]
            else:
                comp_signal = 0.0

            # Rewatch signal
            rewatch_signal = 0.0
            if watch_count > 1:
                rewatch_signal = SIGNAL_WEIGHTS["rewatch"] * min(watch_count - 1, 5)
                rewatch_count += watch_count - 1

            # Recency decay
            days_ago = (now - most_recent).days
            decay = math.exp(-0.693 * days_ago / SIGNAL_WEIGHTS["recency_halflife_days"])

            item_score = (comp_signal + rewatch_signal) * decay
            total_watched += 1
            total_hours += total_duration / 3600
            completions.append(best_completion)

            # Get enrichment metadata
            genres, keywords, cast_names, director_names = [], [], [], []
            if item_key in enrich_cache:
                meta = enrich_cache[item_key]
                genres = meta.get("genres", [])
                keywords = meta.get("keywords", [])
                cast_names = meta.get("cast", [])
                director_names = meta.get("directors", [])

            # Track original language distribution
            orig_lang = enrich_cache.get(item_key, {}).get("original_language")
            if orig_lang:
                language_counts[orig_lang] += 1

            # Animation → Anime reclassification (Japanese origin)
            processed_genres = [
                "Anime" if g == "Animation" and orig_lang == "ja" else g
                for g in genres
            ]

            # Accumulate vectors
            for genre in processed_genres:
                g = genre_scores[genre]
                g["score"] += item_score
                g["count"] += 1
                g["completions"].append(best_completion)
                g["hours"] += total_duration / 3600

            for kw in keywords:
                keyword_scores[kw]["score"] += item_score
                keyword_scores[kw]["count"] += 1

            for name in director_names:
                p = personnel_scores[f"director:{name}"]
                p["score"] += item_score * 1.5
                p["count"] += 1
                p["completions"].append(best_completion)
                p["role"] = "director"

            for name in cast_names:
                p = personnel_scores[f"actor:{name}"]
                p["score"] += item_score
                p["count"] += 1
                p["completions"].append(best_completion)
                p["role"] = "actor"

        profile = normalize_taste_vectors(
            genre_scores, keyword_scores, personnel_scores,
            username, domain, total_watched, total_hours,
            completions, rewatch_count,
        )

        # Build language distribution
        max_lang = max(language_counts.values(), default=1) or 1
        profile.languages = sorted(
            [LanguageAffinity(language=lang, watch_count=cnt,
                              score=round(cnt / max_lang, 3))
             for lang, cnt in language_counts.items()],
            key=lambda l: l.watch_count, reverse=True,
        )
        return profile
