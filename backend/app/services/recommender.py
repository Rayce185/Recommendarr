"""Recommendation Engine — orchestration layer.

Thin engine class that coordinates between:
- rec_types: Shared types and scoring weights
- rec_scoring: Scoring and filtering logic
- rec_library: Library data loading and TMDB helpers
- rec_modes: Mode implementations (tonight, grab, rediscover, group, mood)
- ai_mood / ai_explanations: LLM-powered enhancements
"""

import logging
import random

from app.clients.tautulli import TautulliClient
from app.clients.seerr import SeerrClient
from app.clients.servarr import RadarrClient, SonarrClient
from app.services.taste_profiler import TasteProfiler, TasteProfile
from app.services.ai_mood import parse_mood_ai
from app.services.ai_explanations import generate_explanations, build_profile_summary
from app.services.profile_overrides import get_override_store
from app.services.feedback import get_feedback_store
from app.services.rec_history import log_recommendations, get_recent_rec_map
from app.services.rec_trace import enrich_with_traces, get_watched_titles_for_traces
from app.services.cache import get_cache

# Modular imports
from app.services.rec_types import (
    Recommendation, RecommendationRequest, SCORE_WEIGHTS,
)
from app.services.rec_scoring import score_candidate, apply_filters
from app.services.rec_library import (
    get_library_candidates, candidate_to_recommendation,
    resolve_genre_ids, get_detail, discover_to_candidate,
)
from app.services.rec_modes import mode_tonight, mode_worth_grabbing
from app.services.rec_modes_secondary import (
    mode_rediscover, mode_group_night, mode_mood_match,
)

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Generates recommendations via API orchestration + structured scoring."""

    def __init__(
        self,
        tautulli: TautulliClient,
        seerr: SeerrClient,
        radarr: RadarrClient,
        sonarr_tv: SonarrClient,
        sonarr_anime: SonarrClient,
        profiler: TasteProfiler,
        tmdb=None,
    ):
        self.tautulli = tautulli
        self.seerr = seerr
        self.radarr = radarr
        self.sonarr_tv = sonarr_tv
        self.sonarr_anime = sonarr_anime
        self.profiler = profiler
        self.tmdb = tmdb
        self._library_cache: dict[int, dict] = {}
        self._profile_cache: dict[str, TasteProfile] = {}
        self._genre_cache: dict[str, dict[int, str]] = {}

    async def recommend(self, request: RecommendationRequest) -> list[Recommendation]:
        """Main entry point — route to the appropriate mode."""
        # Resolve username → Tautulli numeric user_id
        from app.services.factory import resolve_user_id
        request._uid = resolve_user_id(request.username)

        # Parse mood text if provided
        if request.mood_text and not request.mood_vector:
            request.mood_vector = await parse_mood_ai(request.mood_text)

        # Load user profile overrides
        override_store = get_override_store()
        request._overrides = override_store.get(request.username)

        # Load user feedback for scoring adjustments
        feedback_store = get_feedback_store()
        request._dismissed_ids = feedback_store.get_dismissed_ids(request.username)
        request._overrides._feedback_liked_genres = feedback_store.get_liked_genres(request.username)
        request._overrides._feedback_disliked_genres = feedback_store.get_disliked_genres(request.username)

        # Dispatch to mode
        mode_map = {
            "tonight": mode_tonight,
            "grab": mode_worth_grabbing,
            "rediscover": mode_rediscover,
            "group": mode_group_night,
            "mood": mode_mood_match,
        }
        handler = mode_map.get(request.mode)
        if not handler:
            logger.warning(f"Unknown mode: {request.mode}")
            return []

        if request.mode == "mood" and not request.mood_vector:
            return []

        results = await handler(self, request)

        # Apply freshness penalty — penalize recently-recommended items (E1)
        if results:
            rec_map = get_recent_rec_map(request.username, days=30)
            if rec_map:
                penalized = 0
                for rec in results:
                    info = rec_map.get(rec.tmdb_id)
                    if info:
                        hours = info["hours_ago"]
                        count = info["count"]
                        # Recency-based penalty
                        if hours < 24:
                            recency_factor = 0.5
                        elif hours < 168:  # 7 days
                            recency_factor = 0.75
                        else:
                            recency_factor = 0.9
                        # Frequency-based penalty (stacks with recency)
                        freq_factor = max(0.6, 1.0 - (count - 1) * 0.08)
                        penalty = recency_factor * freq_factor
                        rec.score = round(rec.score * penalty, 4)
                        rec.score_breakdown["freshness"] = round(penalty, 2)
                        penalized += 1
                if penalized:
                    results.sort(key=lambda r: r.score, reverse=True)
                    logger.debug(f"Freshness: penalized {penalized} items for {request.username}")

        # Apply diversity injection (E2) — prevent genre monotony in top results
        if results and len(results) > 5:
            results = self._diversify_results(results, max_per_genre=3, top_n=15)

        # Generate AI explanations (if enabled + results exist)
        if results and not request.skip_explanations:
            try:
                profile = await self._get_profile(request.username, request.domain)
                profile_summary = build_profile_summary(profile)
                explanations = await generate_explanations(
                    results, profile_summary, mood_text=request.mood_text,
                )
                for rec, expl in zip(results, explanations):
                    rec.explanation = expl
            except Exception as e:
                logger.warning(f"AI explanations skipped: {e}")

        # Enrich with "Because You Watched X" traces
        if results and not request.skip_explanations:
            try:
                watched = await get_watched_titles_for_traces(
                    self.tautulli, self.tmdb,
                    request.username, request._uid, limit=50,
                )
                if watched:
                    enrich_with_traces(results, watched)
            except Exception as e:
                logger.warning(f"Trace enrichment skipped: {e}", exc_info=True)

        # Filter out dismissed items
        dismissed = getattr(request, '_dismissed_ids', set())
        if dismissed:
            before = len(results)
            results = [r for r in results if getattr(r, 'tmdb_id', None) not in dismissed]
            if before != len(results):
                logger.info(f"Filtered {before - len(results)} dismissed items for {request.username}")
        # Apply year and rating filters
        if request.min_year or request.max_year or request.min_rating:
            before = len(results)
            if request.min_year:
                results = [r for r in results if r.year and r.year >= request.min_year]
            if request.max_year:
                results = [r for r in results if r.year and r.year <= request.max_year]
            if request.min_rating:
                results = [r for r in results if r.vote_average and r.vote_average >= request.min_rating]
            if before != len(results):
                logger.info(f"Year/rating filters removed {before - len(results)} items for {request.username}")

        # Log recommendations to history DB (non-blocking best-effort)
        if results:
            try:
                log_recommendations(request.username, results, request.mode)
            except Exception as e:
                logger.warning(f"rec_history logging failed: {e}")

        return results

    # ── Profile and cache management ─────────────────────────────

    async def _get_profile(self, username: str, domain: str) -> TasteProfile:
        """Get or build taste profile (with shared + in-memory caching)."""
        cache_key = f"{username}:{domain}"
        if cache_key not in self._profile_cache:
            shared = get_cache()
            cached = shared.get_profile(username, domain)
            if cached is not None:
                self._profile_cache[cache_key] = cached
            else:
                profile = await self.profiler.build_profile(
                    username=username, domain=domain,
                    enrich_keywords=True, max_enrich=100,
                )
                self._profile_cache[cache_key] = profile
                shared.set_profile(username, domain, profile)
        return self._profile_cache[cache_key]

    def clear_cache(self):
        """Clear all in-memory caches."""
        self._library_cache.clear()
        self._profile_cache.clear()

    def _diversify_results(
        self, recs: list[Recommendation], max_per_genre: int = 3, top_n: int = 15,
    ) -> list[Recommendation]:
        """Enforce genre diversity in top results.

        Ensures no single genre dominates the top_n results by demoting
        excess same-genre items and promoting diverse alternatives.
        """
        if len(recs) <= max_per_genre:
            return recs

        diverse = []
        genre_counts: dict[str, int] = {}
        overflow = []

        for rec in recs:
            primary_genre = rec.genres[0] if rec.genres else "Unknown"
            if len(diverse) < top_n:
                count = genre_counts.get(primary_genre, 0)
                if count < max_per_genre:
                    diverse.append(rec)
                    genre_counts[primary_genre] = count + 1
                else:
                    overflow.append(rec)
            else:
                overflow.append(rec)

        # Fill remaining top_n slots from overflow
        while len(diverse) < top_n and overflow:
            diverse.append(overflow.pop(0))

        # Append remaining overflow after diversified top
        result = diverse + overflow
        return result

    def _shuffle_top_tier(self, recs: list[Recommendation], limit: int) -> list[Recommendation]:
        """Add variety by shuffling within score tiers.

        Top 30% get shuffled for variety; remaining stay ranked.
        """
        if len(recs) <= 3:
            return recs[:limit]
        tier_boundary = max(3, int(len(recs) * 0.3))
        top_tier = recs[:tier_boundary]
        rest = recs[tier_boundary:]
        random.shuffle(top_tier)
        return (top_tier + rest)[:limit]
