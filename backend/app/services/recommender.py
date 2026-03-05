"""Recommendation Engine v2 — API orchestration + structured scoring.

Zero GPU. Zero embeddings. Pure API calls + arithmetic.

Architecture:
  1. Collect candidates (Radarr/Sonarr for in-library, Seerr discover for beyond)
  2. Score candidates against user taste profile + mood vector
  3. Apply collaborative filtering boost from Tautulli peer data
  4. Rank, explain, return

Modes:
  - "tonight": In-library picks → Radarr/Sonarr items scored against taste
  - "grab": Beyond-library → Seerr discover/trending/similar filtered by taste
  - "rediscover": Watched-but-stale → Tautulli old watches with high completion
  - "group": Multi-user intersection (Tautulli histories)
  - "mood": Natural language → MoodVector → score library
"""

import logging
import random
from app.services.cache import get_cache
from dataclasses import dataclass, field
from typing import Optional

from app.clients.tautulli import TautulliClient
from app.clients.seerr import SeerrClient, SeerrMediaDetail, SeerrDiscoverResult
from app.clients.servarr import RadarrClient, SonarrClient, ServarrMovie, ServarrSeries
from app.services.taste_profiler import TasteProfiler, TasteProfile
from app.services.mood_mapper import MoodVector, parse_mood, mood_to_explanation
from app.services.ai_mood import parse_mood_ai
from app.services.ai_explanations import generate_explanations, build_profile_summary
from app.services.profile_overrides import get_override_store, ProfileOverrides
from app.services.feedback import get_feedback_store
from app.utils.genres import normalize_genres

logger = logging.getLogger(__name__)


# ── Scoring weights ──────────────────────────────────────────────

SCORE_WEIGHTS = {
    "genre_match": 0.30,       # How well genres align with taste
    "keyword_match": 0.20,     # TMDB keyword overlap
    "rating_quality": 0.15,    # TMDB/IMDB rating
    "personnel_match": 0.10,   # Director/actor affinity
    "collaborative": 0.10,     # Peer users also watched
    "popularity": 0.05,        # TMDB popularity (tiebreaker)
    "mood_alignment": 0.10,    # Alignment with active mood vector
}


@dataclass
class Recommendation:
    """A scored, explained recommendation."""
    tmdb_id: int
    media_type: str              # "movie" | "tv"
    title: str
    year: Optional[int] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    overview: Optional[str] = None
    vote_average: float = 0.0
    runtime: Optional[int] = None
    original_language: Optional[str] = None
    # Scoring
    score: float = 0.0           # 0.0–1.0
    score_breakdown: dict = field(default_factory=dict)
    explanation: str = ""
    explanation_signals: list[str] = field(default_factory=list)
    # Context
    mode: str = "tonight"
    in_library: bool = False
    is_watched: bool = False
    quality: Optional[str] = None
    source: Optional[str] = None   # "trending" | "similar" | "discover" | "collaborative"
    # Credits
    directors: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    # Trailers
    trailer_key: Optional[str] = None
    trailer_site: Optional[str] = None


@dataclass
class RecommendationRequest:
    """Input parameters for generating recommendations."""
    username: str
    mode: str = "tonight"          # "tonight" | "grab" | "rediscover" | "group" | "mood"
    mood_text: Optional[str] = None
    mood_vector: Optional[MoodVector] = None
    mood_profile_id: Optional[int] = None
    domain: str = "all"            # "movies" | "tv" | "anime" | "all"
    genre_filter: Optional[str] = None
    limit: int = 20
    exclude_tmdb_ids: set[int] = field(default_factory=set)
    exclude_genres: set[str] = field(default_factory=set)
    include_genres: set[str] = field(default_factory=set)
    exclude_libraries: set[str] = field(default_factory=set)
    group_users: list[str] = field(default_factory=list)  # For group mode
    skip_explanations: bool = False  # Skip AI explanation generation (for refresh/pre-warm)


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
        self.tmdb = tmdb  # TMDBClient — preferred over Seerr when available
        # Caches (per-session, refreshed on demand)
        self._library_cache: dict[int, dict] = {}
        self._profile_cache: dict[str, TasteProfile] = {}
        self._genre_cache: dict[str, dict[int, str]] = {}  # {movie: {id: name}, tv: {id: name}}

    async def recommend(self, request: RecommendationRequest) -> list[Recommendation]:
        """Main entry point — route to the appropriate mode."""
        # Resolve username → Tautulli numeric user_id for history filtering
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
        # Attach feedback genre data to overrides for scoring
        request._overrides._feedback_liked_genres = feedback_store.get_liked_genres(request.username)
        request._overrides._feedback_disliked_genres = feedback_store.get_disliked_genres(request.username)

        if request.mode == "tonight":
            results = await self._tonight(request)
        elif request.mode == "grab":
            results = await self._worth_grabbing(request)
        elif request.mode == "rediscover":
            results = await self._rediscover(request)
        elif request.mode == "group":
            results = await self._group_night(request)
        elif request.mode == "mood":
            if not request.mood_vector:
                return []
            results = await self._mood_match(request)
        else:
            logger.warning(f"Unknown mode: {request.mode}")
            return []

        # Generate AI explanations (if enabled + we have results)
        if results and not request.skip_explanations:
            try:
                profile = await self._get_profile(request.username, request.domain)
                profile_summary = build_profile_summary(profile)
                explanations = await generate_explanations(
                    results,
                    profile_summary,
                    mood_text=request.mood_text,
                )
                for rec, expl in zip(results, explanations):
                    rec.explanation = expl
            except Exception as e:
                logger.warning(f"AI explanations skipped: {e}")

        # Filter out dismissed items
        dismissed = getattr(request, '_dismissed_ids', set())
        if dismissed:
            before = len(results)
            results = [r for r in results if getattr(r, 'tmdb_id', None) not in dismissed]
            if before != len(results):
                logger.info(f"Filtered {before - len(results)} dismissed items for {request.username}")
        return results

    # ── Mode: Watch Tonight ──────────────────────────────────────

    async def _tonight(self, req: RecommendationRequest) -> list[Recommendation]:
        """In-library recommendations scored against user taste.

        Uses Plex viewCount to exclude already-watched items.
        Uses Plex library section to penalize content from irrelevant libraries.
        Deterministic scoring — no random shuffling.
        """
        profile = await self._get_profile(req.username, req.domain)

        # Collect library candidates from Radarr/Sonarr
        candidates = await self._get_library_candidates(req.domain)
        candidates = self._apply_filters(candidates, req)

        # Get Plex client for watched exclusion + section awareness
        from app.services.factory import get_stack
        stack = get_stack()
        plex = stack.plex if stack else None

        # Build user's watch-by-section profile (which libraries they actually use)
        user_section_counts: dict[str, int] = {}
        if plex and plex._watched_map:
            for key, vc in plex._watched_map.items():
                sec = plex._section_map.get(key, "")
                if sec:
                    user_section_counts[sec] = user_section_counts.get(sec, 0) + vc

        # Score each candidate
        scored = []
        for candidate in candidates:
            tmdb_id = candidate.get("tmdb_id", 0)
            media_type = candidate.get("media_type", "movie")

            if tmdb_id in req.exclude_tmdb_ids:
                continue

            # Tag watched status (don't exclude — user may want to rewatch)
            is_watched = plex.is_watched(tmdb_id, media_type) if plex else False

            if req.genre_filter and req.genre_filter not in candidate.get("genres", []):
                continue

            score, breakdown, signals = self._score_candidate(candidate, profile, req.mood_vector, getattr(req, '_overrides', None))

            # Section relevance: penalize items from libraries the user never/rarely watches
            if plex and user_section_counts:
                section = plex.get_section_name(tmdb_id, media_type)
                if section:
                    sec_watches = user_section_counts.get(section, 0)
                    total_watches = sum(user_section_counts.values())
                    sec_ratio = sec_watches / total_watches if total_watches > 0 else 0
                    if sec_ratio < 0.02:
                        score *= 0.3
                        signals.append(f"Low affinity: {section}")
                    elif sec_ratio < 0.10:
                        score *= 0.6
                        signals.append(f"Moderate affinity: {section}")

            rec = self._candidate_to_recommendation(candidate, score, breakdown, signals, "tonight")
            rec.is_watched = is_watched
            scored.append(rec)

        # Sort strictly by score — deterministic, no randomness
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:req.limit]


    # ── Mode: Worth Grabbing ─────────────────────────────────────

    async def _worth_grabbing(self, req: RecommendationRequest) -> list[Recommendation]:
        """Beyond-library recommendations from TMDB discover/trending via Seerr."""
        profile = await self._get_profile(req.username, req.domain)

        # Get library TMDB IDs to exclude (already have these)
        library_tmdb_ids = await self._get_library_tmdb_ids(req.domain)
        exclude = req.exclude_tmdb_ids | library_tmdb_ids

        # Collect candidates from multiple Seerr sources
        candidates: list[dict] = []

        # Source 1: Trending
        trending = await self._get_trending(page=1)
        for item in trending:
            if item.tmdb_id not in exclude:
                candidates.append(await self._discover_to_candidate(item, "trending"))

        # Source 2: TMDB discover filtered by top genres
        top_genres = profile.top_genres(3)
        # Genre ID lookup from TMDB (cache populated on first resolve)
        if not self._genre_cache.get("movie"):
            await self._resolve_genre_ids([], "movie")  # Populate cache
        reverse_genre_map = {v: k for k, v in self._genre_cache.get("movie", {}).items()}
        for ga in top_genres:
            genre_id = reverse_genre_map.get(ga.genre)
            if genre_id:
                discovered = await self._discover_by_genre(genre_id, "movie", page=1)
                for item in discovered[:10]:
                    if item.tmdb_id not in exclude:
                        candidates.append(await self._discover_to_candidate(item, "discover"))

        # Source 3: Similar to user's top-rated watched titles
        # Get a few high-completion titles from history
        history = await self.tautulli.get_history(user_id=None, limit=3000)
        user_events = [e for e in history if e.user_id == req._uid and e.tmdb_id and e.completion_pct >= 85]
        # Pick up to 3 random high-completion titles as similarity seeds
        seeds = random.sample(user_events, min(3, len(user_events))) if user_events else []
        for seed in seeds:
            similar = await self._get_similar(seed.tmdb_id, "movie", page=1)
            for item in similar[:8]:
                if item.tmdb_id not in exclude:
                    candidates.append(await self._discover_to_candidate(item, "similar"))

        # Deduplicate by tmdb_id (keep first occurrence = best source)
        seen = set()
        unique = []
        for c in candidates:
            tid = c.get("tmdb_id", 0)
            if tid not in seen:
                seen.add(tid)
                unique.append(c)
        candidates = unique
        candidates = self._apply_filters(candidates, req)

        # Enrich top candidates with keywords via Seerr (up to 40)
        for c in candidates[:40]:
            try:
                detail = await self._get_detail(c["tmdb_id"], c.get("media_type", "movie"))
                c["keywords"] = detail["keywords"]
                c["directors"] = detail["directors"]
                c["cast"] = [x["name"] if isinstance(x, dict) else x for x in detail.get("cast", [])[:5]]
                c["overview"] = detail["overview"]
                c["runtime"] = detail.get("runtime")
                c["original_language"] = detail.get("original_language")
                if detail.get("trailers"):
                    c["trailer_key"] = detail["trailers"][0].get("key")
                    c["trailer_site"] = detail["trailers"][0].get("site")
            except Exception as e:
                logger.debug(f"Enrich failed for {c.get('tmdb_id')}: {e}")

        # Score
        scored = []
        for candidate in candidates:
            if req.genre_filter and req.genre_filter not in candidate.get("genres", []):
                continue
            score, breakdown, signals = self._score_candidate(candidate, profile, req.mood_vector, getattr(req, '_overrides', None))
            rec = self._candidate_to_recommendation(candidate, score, breakdown, signals, "grab")
            scored.append(rec)

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:req.limit]

    # ── Mode: Rediscover ─────────────────────────────────────────

    async def _rediscover(self, req: RecommendationRequest) -> list[Recommendation]:
        """Titles the user watched and liked, but haven't touched in a while."""
        cache = get_cache()
        history = await self.tautulli.get_history(user_id=None, limit=10000)
        user_events = [e for e in history if e.user_id == req._uid]

        # Group by item
        from collections import defaultdict
        by_item: dict[str, list] = defaultdict(list)
        for e in user_events:
            by_item[e.item_key].append(e)

        # Find items with high completion but old last watch
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        stale_threshold = now - timedelta(days=180)  # 6+ months ago

        # First pass: collect candidates by staleness/completion (no TMDB resolution yet)
        pre_candidates = []
        for item_key, events in by_item.items():
            best_completion = max(e.completion_pct for e in events)
            most_recent = max((e.started_at for e in events if e.started_at), default=None)

            if best_completion < 70:
                continue  # Didn't enjoy it enough
            if most_recent and most_recent.tzinfo is None:
                most_recent = most_recent.replace(tzinfo=timezone.utc)
            if most_recent and most_recent > stale_threshold:
                continue  # Watched too recently

            days_since = (now - most_recent).days if most_recent else 365
            pre_candidates.append({
                "item_key": item_key,
                "media_type": events[0].media_type,
                "tmdb_id": events[0].tmdb_id,
                "best_completion": best_completion,
                "days_since": days_since,
                "watch_count": len(events),
                "staleness_score": min(1.0, days_since / 730),
            })

        # Sort by quality, then resolve TMDB IDs only for top candidates
        pre_candidates.sort(
            key=lambda c: c["staleness_score"] * (c["best_completion"] / 100),
            reverse=True,
        )
        pre_candidates = pre_candidates[:req.limit * 3]

        # Resolve missing TMDB IDs (limited to top candidates only)
        candidates = []
        for c in pre_candidates:
            tmdb_id = c["tmdb_id"]
            if not tmdb_id:
                # Check TMDB ID cache first
                cached_tmdb = cache.get_tmdb_id(c["item_key"])
                if cached_tmdb is not None:
                    tmdb_id = cached_tmdb
                else:
                    try:
                        tmdb_id = await self.tautulli.resolve_tmdb_id(
                            c["item_key"], c["media_type"]
                        )
                        cache.set_tmdb_id(c["item_key"], tmdb_id)
                    except Exception:
                        pass
            if not tmdb_id or tmdb_id in req.exclude_tmdb_ids:
                continue
            c["tmdb_id"] = tmdb_id
            candidates.append({
                "tmdb_id": tmdb_id,
                "media_type": c["media_type"],
                "item_key": c["item_key"],
                "best_completion": c["best_completion"],
                "watch_count": c["watch_count"],
                "days_since": c["days_since"],
                "staleness_score": c["staleness_score"],
            })

        # Already sorted; trim to limit
        candidates = self._apply_filters(candidates, req)
        candidates = candidates[:req.limit * 2]

        # Enrich from Seerr
        scored = []
        for c in candidates[:req.limit]:
            try:
                media_type = "movie" if c["media_type"] == "movie" else "tv"
                detail = await self._get_detail(c["tmdb_id"], media_type)
                rec = Recommendation(
                    tmdb_id=c["tmdb_id"],
                    media_type=media_type,
                    title=detail["title"],
                    year=detail.get("year"),
                    poster_path=detail.get("poster_path"),
                    backdrop_path=detail.get("backdrop_path"),
                    genres=normalize_genres(detail.get("genres", []), original_language=detail.get("original_language")),
                    keywords=detail.get("keywords", [])[:10],
                    overview=detail.get("overview", ""),
                    vote_average=detail.get("vote_average", 0),
                    runtime=detail.get("runtime"),
                    original_language=detail.get("original_language"),
                    score=c["staleness_score"] * (c["best_completion"] / 100),
                    score_breakdown={"staleness": c["staleness_score"], "completion": c["best_completion"]},
                    mode="rediscover",
                    in_library=True,
                    directors=detail.get("directors", []),
                    cast=[x["name"] if isinstance(x, dict) else x for x in detail.get("cast", [])[:5]],
                    trailer_key=detail.get("trailers", [{}])[0].get("key") if detail.get("trailers") else None,
                )
                # Explanation
                signals = []
                if c["days_since"] > 365:
                    signals.append(f"Last watched {c['days_since'] // 365} years ago")
                else:
                    signals.append(f"Last watched {c['days_since'] // 30} months ago")
                if c["watch_count"] > 1:
                    signals.append(f"Watched {c['watch_count']} times")
                signals.append(f"{c['best_completion']:.0f}% completion")
                rec.explanation = " · ".join(signals)
                rec.explanation_signals = signals
                scored.append(rec)
            except Exception as e:
                logger.debug(f"Rediscover enrich failed: {e}")

        return scored

    # ── Mode: Group Night ────────────────────────────────────────

    async def _group_night(self, req: RecommendationRequest) -> list[Recommendation]:
        """Find titles matching taste intersection of multiple users."""
        if len(req.group_users) < 2:
            return []

        # Build profiles for all group members
        profiles = {}
        for user in req.group_users:
            profiles[user] = await self._get_profile(user, req.domain)

        # Get library candidates
        candidates = await self._get_library_candidates(req.domain)
        candidates = self._apply_filters(candidates, req)

        # Score each candidate against ALL profiles, take the minimum
        # (ensures everyone enjoys it, not just one person)
        scored = []
        for candidate in candidates:
            if candidate.get("tmdb_id", 0) in req.exclude_tmdb_ids:
                continue

            scores_per_user = {}
            for user, profile in profiles.items():
                score, breakdown, signals = self._score_candidate(candidate, profile, req.mood_vector, getattr(req, '_overrides', None))
                scores_per_user[user] = score

            # Group score = minimum individual score (weakest link)
            group_score = min(scores_per_user.values()) if scores_per_user else 0
            avg_score = sum(scores_per_user.values()) / len(scores_per_user) if scores_per_user else 0

            # Weighted: 70% min + 30% avg (ensures nobody hates it, but favors universal appeal)
            final_score = 0.7 * group_score + 0.3 * avg_score

            rec = self._candidate_to_recommendation(candidate, final_score, {"per_user": scores_per_user}, [], "group")
            rec.explanation = f"Group fit: {' / '.join(f'{u}:{s:.0%}' for u, s in scores_per_user.items())}"
            scored.append(rec)

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:req.limit]

    # ── Mode: Mood Match ─────────────────────────────────────────

    async def _mood_match(self, req: RecommendationRequest) -> list[Recommendation]:
        """Apply mood vector to library, combining with taste profile."""
        profile = await self._get_profile(req.username, req.domain)
        candidates = await self._get_library_candidates(req.domain)
        candidates = self._apply_filters(candidates, req)

        scored = []
        for candidate in candidates:
            if candidate.get("tmdb_id", 0) in req.exclude_tmdb_ids:
                continue

            # Score with mood vector weighted heavily
            score, breakdown, signals = self._score_candidate(candidate, profile, req.mood_vector, getattr(req, '_overrides', None))
            rec = self._candidate_to_recommendation(candidate, score, breakdown, signals, "mood")
            scored.append(rec)

        scored.sort(key=lambda r: r.score, reverse=True)
        result = scored[:req.limit]

        # Prepend mood explanation to each
        mood_explanation = mood_to_explanation(req.mood_vector)
        for rec in result:
            rec.explanation = f"Mood: {mood_explanation} · {rec.explanation}"

        return result

    # ── Scoring Engine ───────────────────────────────────────────

    def _apply_filters(self, candidates: list[dict], req) -> list[dict]:
        """Apply genre and library section filters to candidate list."""
        filtered = candidates

        # Genre exclusion
        if req.exclude_genres:
            excl = {g.lower() for g in req.exclude_genres}
            filtered = [
                c for c in filtered
                if not any(
                    (g.lower() if isinstance(g, str) else g.get("name", "").lower()) in excl
                    for g in c.get("genres", [])
                )
            ]

        # Genre inclusion (keep only items that have at least one included genre)
        if req.include_genres:
            incl = {g.lower() for g in req.include_genres}
            filtered = [
                c for c in filtered
                if any(
                    (g.lower() if isinstance(g, str) else g.get("name", "").lower()) in incl
                    for g in c.get("genres", [])
                )
            ]

        # Library section exclusion (requires Plex client)
        if req.exclude_libraries:
            from app.services.factory import get_stack
            stack = get_stack()
            if stack.plex:
                excl_libs = req.exclude_libraries
                filtered = [
                    c for c in filtered
                    if not stack.plex.is_in_section(
                        c.get("tmdb_id", 0),
                        c.get("media_type", "movie"),
                        excl_libs,
                    )
                ]

        return filtered

    def _score_candidate(
        self,
        candidate: dict,
        profile: TasteProfile,
        mood: Optional[MoodVector] = None,
        overrides: Optional[ProfileOverrides] = None,
    ) -> tuple[float, dict, list[str]]:
        """Score a single candidate against a taste profile, optional mood, and user overrides.

        Returns (total_score, breakdown_dict, explanation_signals).
        """
        breakdown = {}
        signals = []

        # 1. Genre match
        c_genres = candidate.get("genres", [])
        if c_genres and profile.genres:
            genre_scores = [profile.genre_score(g) for g in c_genres]
            genre_match = max(genre_scores) if genre_scores else 0.0
            breakdown["genre"] = genre_match
            if genre_match > 0.7:
                top_genre = c_genres[genre_scores.index(max(genre_scores))] if genre_scores else ""
                signals.append(f"Strong {top_genre} affinity")
        else:
            breakdown["genre"] = 0.0

        # 1b. Apply profile overrides for genres
        if overrides:
            c_genres = candidate.get("genres", [])
            # Hard block: if any genre is in blocked list, score 0
            for g in c_genres:
                if g in overrides.genre_blocks:
                    return 0.0, breakdown, [f"Blocked genre: {g}"]
            # Soft boost: adjust genre score based on user preference
            genre_boost_total = 0.0
            for g in c_genres:
                if g in overrides.genre_boosts:
                    genre_boost_total += overrides.genre_boosts[g]
            if c_genres:
                avg_boost = genre_boost_total / len(c_genres)
                breakdown["genre"] = max(0.0, min(1.0, breakdown.get("genre", 0) + avg_boost))

        # 2. Keyword match
        c_keywords = candidate.get("keywords", [])
        if c_keywords and profile.keywords:
            kw_scores = [profile.keyword_score(k) for k in c_keywords]
            kw_match = (sum(s for s in kw_scores if s > 0) / max(len(c_keywords), 1))
            breakdown["keyword"] = min(1.0, kw_match * 2)  # Scale up since keyword scores are sparse
            if kw_match > 0.3:
                matched = [k for k, s in zip(c_keywords, kw_scores) if s > 0.3][:2]
                if matched:
                    signals.append(f"Keywords: {', '.join(matched)}")
        else:
            breakdown["keyword"] = 0.0

        # 2b. Apply keyword overrides
        if overrides:
            c_keywords = candidate.get("keywords", [])
            for kw in c_keywords:
                if kw in overrides.keyword_blocks:
                    breakdown["keyword"] = max(0.0, breakdown.get("keyword", 0) - 0.3)
                if kw in overrides.keyword_boosts:
                    breakdown["keyword"] = min(1.0, breakdown.get("keyword", 0) + 0.2)

        # 2c. Apply feedback-based genre adjustments
        liked_g = getattr(overrides, '_feedback_liked_genres', {}) if overrides else {}
        disliked_g = getattr(overrides, '_feedback_disliked_genres', {}) if overrides else {}
        c_genres_lower = candidate.get("genres", [])
        if liked_g:
            for g in c_genres_lower:
                if g in liked_g:
                    boost = min(0.15, liked_g[g] * 0.05)
                    breakdown["genre"] = min(1.0, breakdown.get("genre", 0) + boost)
                    if boost >= 0.1:
                        signals.append(f"Liked similar {g} titles")
        if disliked_g:
            for g in c_genres_lower:
                if g in disliked_g:
                    penalty = min(0.15, disliked_g[g] * 0.05)
                    breakdown["genre"] = max(0.0, breakdown.get("genre", 0) - penalty)

        # 3. Rating quality
        vote_avg = candidate.get("vote_average", 0) or 0
        rating_score = min(1.0, max(0.0, (vote_avg - 5.0) / 4.5))  # 5.0→0, 9.5→1.0
        breakdown["rating"] = rating_score
        if vote_avg >= 8.0:
            signals.append(f"Highly rated ({vote_avg:.1f})")

        # 4. Personnel match
        c_directors = candidate.get("directors", [])
        c_cast = candidate.get("cast", [])
        personnel_score = 0.0
        for name in c_directors:
            for p in profile.personnel:
                if p.name == name and p.role == "director":
                    personnel_score = max(personnel_score, p.score)
                    if p.score > 0.5:
                        signals.append(f"Director: {name}")
        for name in c_cast[:3]:
            for p in profile.personnel:
                if p.name == name and p.role == "actor":
                    personnel_score = max(personnel_score, p.score * 0.7)
        breakdown["personnel"] = personnel_score

        # 5. Popularity (normalized)
        popularity = candidate.get("popularity", 0) or 0
        breakdown["popularity"] = min(1.0, popularity / 100)

        # 6. Mood alignment (if mood vector provided)
        mood_score = 0.0
        if mood:
            # Check genre alignment
            for genre in c_genres:
                if genre in mood.genre_boost:
                    mood_score += mood.genre_boost[genre]
                if genre in mood.genre_block:
                    return 0.0, breakdown, ["Blocked by mood filter"]  # Hard filter

            # Check keyword alignment
            for kw in c_keywords:
                if kw in mood.keyword_boost:
                    mood_score += 0.3
                if kw in mood.keyword_block:
                    mood_score -= 0.5

            # Runtime filter
            runtime = candidate.get("runtime") or 0
            if mood.max_runtime and runtime > mood.max_runtime:
                mood_score -= 0.5
            if mood.min_runtime and runtime < mood.min_runtime:
                mood_score -= 0.3

            # Year filter
            year = candidate.get("year") or 0
            if mood.year_range:
                if year < mood.year_range[0] or year > mood.year_range[1]:
                    mood_score -= 0.5

            # Rating filter
            if mood.min_rating and vote_avg < mood.min_rating:
                mood_score -= 0.3

            mood_score = max(0.0, min(1.0, mood_score))
            breakdown["mood"] = mood_score
        else:
            breakdown["mood"] = 0.5  # Neutral when no mood

        # Weighted total
        total = (
            breakdown.get("genre", 0) * SCORE_WEIGHTS["genre_match"]
            + breakdown.get("keyword", 0) * SCORE_WEIGHTS["keyword_match"]
            + breakdown.get("rating", 0) * SCORE_WEIGHTS["rating_quality"]
            + breakdown.get("personnel", 0) * SCORE_WEIGHTS["personnel_match"]
            + breakdown.get("popularity", 0) * SCORE_WEIGHTS["popularity"]
            + breakdown.get("mood", 0.5) * SCORE_WEIGHTS["mood_alignment"]
        )

        # Generate explanation string
        explanation = " · ".join(signals) if signals else f"Score: {total:.0%}"

        return round(total, 4), breakdown, signals

    # ── Library candidate collection ─────────────────────────────

    async def _get_library_candidates(self, domain: str = "all") -> list[dict]:
        """Collect all library items from Radarr/Sonarr as candidate dicts."""
        cache = get_cache()
        cached = cache.get_library(domain)
        if cached is not None:
            return cached

        candidates = []

        if domain in ("all", "movies"):
            movies = await self.radarr.get_all_movies()
            for m in movies:
                if not m.tmdb_id:
                    continue
                candidates.append({
                    "tmdb_id": m.tmdb_id,
                    "media_type": "movie",
                    "title": m.title,
                    "year": m.year,
                    "genres": normalize_genres(m.genres, original_language=m.original_language if hasattr(m, 'original_language') else None),
                    "overview": m.overview,
                    "vote_average": m.vote_average,
                    "runtime": m.runtime_minutes,
                    "original_language": m.original_language if hasattr(m, 'original_language') else None,
                    "poster_path": m.poster_path,
                    "imdb_id": m.imdb_id,
                    "in_library": True,
                    "quality": m.quality if hasattr(m, 'quality') else None,
                    "keywords": [],  # Enriched on-demand
                    "directors": [],
                    "cast": [],
                    "popularity": m.popularity if hasattr(m, 'popularity') else 0,
                })

        if domain in ("all", "tv"):
            series = await self.sonarr_tv.get_all_series()
            for s in series:
                if not s.tmdb_id:
                    continue
                candidates.append({
                    "tmdb_id": s.tmdb_id,
                    "media_type": "tv",
                    "title": s.title,
                    "year": s.year,
                    "genres": normalize_genres(s.genres, original_language=s.original_language if hasattr(s, 'original_language') else None),
                    "overview": s.overview,
                    "vote_average": s.vote_average,
                    "runtime": s.runtime_minutes if hasattr(s, 'runtime_minutes') else None,
                    "poster_path": s.poster_path,
                    "in_library": True,
                    "keywords": [],
                    "directors": [],
                    "cast": [],
                    "popularity": 0,
                })

        if domain in ("all", "anime"):
            anime = await self.sonarr_anime.get_all_series()
            for s in anime:
                if not s.tmdb_id:
                    continue
                candidates.append({
                    "tmdb_id": s.tmdb_id,
                    "media_type": "tv",
                    "title": s.title,
                    "year": s.year,
                    "genres": normalize_genres(s.genres, is_anime_source=True),
                    "overview": s.overview,
                    "vote_average": s.vote_average,
                    "runtime": s.runtime_minutes if hasattr(s, 'runtime_minutes') else None,
                    "poster_path": s.poster_path,
                    "in_library": True,
                    "keywords": ["anime"],  # We know this is from anime Sonarr
                    "directors": [],
                    "cast": [],
                    "popularity": 0,
                })

        self._fix_poster_urls(candidates)
        cache.set_library(domain, candidates)
        return candidates

    def _fix_poster_urls(self, candidates: list[dict]) -> None:
        """Replace TVDB poster URLs with TMDB paths from cache.
        
        Sonarr returns TVDB poster URLs which get hotlink-blocked in browsers.
        This does a bulk lookup against tmdb_cache and swaps them for TMDB paths.
        Items not in cache are queued for background TMDB enrichment.
        """
        # Find candidates with TVDB (or other non-TMDB) poster URLs
        needs_fix = []
        for c in candidates:
            pp = c.get("poster_path") or ""
            if pp.startswith("http") and "image.tmdb.org" not in pp:
                needs_fix.append(c)
        
        if not needs_fix:
            return
        
        # Bulk lookup tmdb_cache for TMDB poster paths
        try:
            from app.database import get_db
            from app.models.tables import TmdbCache
            from sqlalchemy import select, and_
            
            tmdb_ids = [c["tmdb_id"] for c in needs_fix]
            poster_map = {}  # tmdb_id -> tmdb_poster_path
            
            with get_db() as db:
                rows = db.execute(
                    select(TmdbCache.tmdb_id, TmdbCache.poster_path).where(
                        TmdbCache.tmdb_id.in_(tmdb_ids),
                        TmdbCache.poster_path.isnot(None),
                        TmdbCache.poster_path != "",
                    )
                ).all()
                for row in rows:
                    # Only use paths that look like TMDB paths (start with /)
                    if row.poster_path and row.poster_path.startswith("/"):
                        poster_map[row.tmdb_id] = row.poster_path
            
            fixed = 0
            still_broken = 0
            for c in needs_fix:
                tmdb_poster = poster_map.get(c["tmdb_id"])
                if tmdb_poster:
                    c["poster_path"] = tmdb_poster
                    fixed += 1
                else:
                    still_broken += 1
            
            if fixed or still_broken:
                logger.info(f"Poster fix: {fixed} swapped TVDB→TMDB, {still_broken} still need enrichment")
        except Exception as e:
            logger.warning(f"Poster URL fix failed: {e}")

    async def _get_library_tmdb_ids(self, domain: str = "all") -> set[int]:
        """Get set of all TMDB IDs in the library (for dedup in grab mode)."""
        candidates = await self._get_library_candidates(domain)
        return {c["tmdb_id"] for c in candidates if c.get("tmdb_id")}

    # ── Helpers ──────────────────────────────────────────────────

    async def _resolve_genre_ids(self, genre_ids: list[int], media_type: str) -> list[str]:
        """Resolve TMDB genre IDs to names using TMDB API (with caching)."""
        if self.tmdb:
            if media_type not in self._genre_cache:
                try:
                    if media_type == "movie":
                        genres = await self.tmdb.get_movie_genres()
                    else:
                        genres = await self.tmdb.get_tv_genres()
                    self._genre_cache[media_type] = {g["id"]: g["name"] for g in genres}
                except Exception:
                    self._genre_cache[media_type] = {}
            return [self._genre_cache[media_type].get(gid, f"Genre:{gid}") for gid in genre_ids
                    if gid in self._genre_cache.get(media_type, {})]
        # Fallback to Seerr
        return self.seerr.resolve_genre_ids(genre_ids, media_type)

    async def _get_detail(self, tmdb_id: int, media_type: str) -> dict:
        """Get detail from TMDB (preferred) or Seerr, returning a normalized dict."""
        if self.tmdb:
            d = await self.tmdb.get_detail(tmdb_id, media_type)
            return {
                "title": d.get("title", ""),
                "year": d.get("year"),
                "poster_path": d.get("poster_path"),
                "backdrop_path": d.get("backdrop_path"),
                "genres": d.get("genres", []),
                "keywords": d.get("keywords", []),
                "overview": d.get("overview", ""),
                "vote_average": d.get("vote_average", 0),
                "runtime": d.get("runtime"),
                "original_language": d.get("original_language"),
                "directors": [c["name"] for c in d.get("crew", []) if c.get("job") == "Director"],
                "cast": d.get("cast", []),
                "trailers": [],  # TMDB detail doesn't include videos by default
            }
        # Fallback to Seerr
        detail = await self.seerr.get_detail(tmdb_id, media_type)
        return {
            "title": detail.title,
            "year": detail.year,
            "poster_path": detail.poster_path,
            "backdrop_path": detail.backdrop_path,
            "genres": normalize_genres(detail.genres, original_language=getattr(detail, 'original_language', None)),
            "keywords": detail.keywords,
            "overview": detail.overview,
            "vote_average": detail.vote_average,
            "runtime": detail.runtime,
            "original_language": detail.original_language,
            "directors": detail.directors,
            "cast": detail.cast,
            "trailers": detail.trailers if hasattr(detail, "trailers") else [],
        }

    async def _get_trending(self, page: int = 1):
        """Get trending from TMDB (preferred) or Seerr."""
        if self.tmdb:
            results, _ = await self.tmdb.get_trending("all", "week", page)
            return results
        return await self.seerr.get_trending(page)

    async def _discover_by_genre(self, genre_id: int, media_type: str = "movie", page: int = 1):
        """Discover by genre from TMDB (preferred) or Seerr."""
        if self.tmdb:
            return await self.tmdb.discover_by_genre(genre_id, media_type, page)
        if media_type == "movie":
            return await self.seerr.discover_movies(page=page, genre=genre_id)
        return await self.seerr.discover_tv(page=page, genre=genre_id)

    async def _get_similar(self, tmdb_id: int, media_type: str = "movie", page: int = 1):
        """Get similar titles from TMDB (preferred) or Seerr."""
        if self.tmdb:
            return await self.tmdb.get_similar(tmdb_id, media_type, page)
        return await self.seerr.get_similar(tmdb_id, media_type, page)

    async def _discover_to_candidate(self, item, source: str) -> dict:
        """Convert Seerr discover result to candidate dict."""
        return {
            "tmdb_id": item.tmdb_id,
            "media_type": item.media_type,
            "title": item.title,
            "year": item.year,
            "genres": normalize_genres(await self._resolve_genre_ids(item.genre_ids, item.media_type) if hasattr(item, 'genre_ids') else item.genres if hasattr(item, 'genres') else [], original_language=getattr(item, 'original_language', None)),
            "overview": item.overview,
            "vote_average": item.vote_average,
            "poster_path": item.poster_path,
            "in_library": False,
            "source": source,
            "keywords": [],
            "directors": [],
            "cast": [],
            "popularity": item.popularity,
            "runtime": None,
            "original_language": None,
        }

    def _candidate_to_recommendation(
        self,
        candidate: dict,
        score: float,
        breakdown: dict,
        signals: list[str],
        mode: str,
    ) -> Recommendation:
        """Convert a scored candidate dict to a Recommendation object."""
        return Recommendation(
            tmdb_id=candidate.get("tmdb_id", 0),
            media_type=candidate.get("media_type", "movie"),
            title=candidate.get("title", ""),
            year=candidate.get("year"),
            poster_path=candidate.get("poster_path"),
            backdrop_path=candidate.get("backdrop_path"),
            genres=candidate.get("genres", []),
            keywords=candidate.get("keywords", [])[:10],
            overview=candidate.get("overview"),
            vote_average=candidate.get("vote_average", 0),
            runtime=candidate.get("runtime"),
            original_language=candidate.get("original_language"),
            score=score,
            score_breakdown=breakdown,
            explanation=" · ".join(signals) if signals else "",
            explanation_signals=signals,
            mode=mode,
            in_library=candidate.get("in_library", False),
            quality=candidate.get("quality"),
            source=candidate.get("source"),
            directors=candidate.get("directors", []),
            cast=candidate.get("cast", []),
            trailer_key=candidate.get("trailer_key"),
            trailer_site=candidate.get("trailer_site"),
        )

    def _shuffle_top_tier(self, recs: list[Recommendation], limit: int) -> list[Recommendation]:
        """Add variety by shuffling within score tiers.

        Top 30% of results get shuffled so it's not the same order every time.
        Remaining 70% stay ranked. Then truncate to limit.
        """
        if len(recs) <= 3:
            return recs[:limit]

        tier_boundary = max(3, int(len(recs) * 0.3))
        top_tier = recs[:tier_boundary]
        rest = recs[tier_boundary:]

        random.shuffle(top_tier)
        return (top_tier + rest)[:limit]

    async def _get_profile(self, username: str, domain: str) -> TasteProfile:
        """Get or build taste profile (with shared + in-memory caching)."""
        cache_key = f"{username}:{domain}"
        if cache_key not in self._profile_cache:
            # Check shared cache first
            from app.services.cache import get_cache
            shared = get_cache()
            cached = shared.get_profile(username, domain)
            if cached is not None:
                self._profile_cache[cache_key] = cached
            else:
                profile = await self.profiler.build_profile(
                    username=username,
                    domain=domain,
                    enrich_keywords=True,
                    max_enrich=100,
                )
                self._profile_cache[cache_key] = profile
                shared.set_profile(username, domain, profile)
        return self._profile_cache[cache_key]

    def clear_cache(self):
        """Clear all in-memory caches."""
        self._library_cache.clear()
        self._profile_cache.clear()
