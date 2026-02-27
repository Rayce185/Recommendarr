"""Taste profiler — builds user preference vectors from watch history.

Creates sub-profiles per media domain (Movies, TV, Anime) with:
- Genre affinity weights (from completion rates, not just watch count)
- Personnel affinity (directors, actors who predict completion)
- Anti-profile (genres/themes the user abandons)
- Temporal decay (recent watches count more)
- Cross-pollination controls
"""

import math
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import (
    User, WatchHistory, TmdbCache, UserLibraryAccess,
    Feedback, InfluenceOverride,
)

logger = logging.getLogger(__name__)


# ── Signal weight constants (from spec §3.1) ────────────────────

SIGNAL_WEIGHTS = {
    "completion_full": 5.0,       # Watched ≥85%
    "completion_partial": 2.0,    # Watched 40-84%
    "completion_abandoned": -3.0, # Abandoned <20%
    "rewatch": 4.0,               # Watched more than once
    "user_rating_high": 3.0,      # Rating ≥8
    "user_rating_low": -2.0,      # Rating ≤4
    "feedback_up": 3.0,           # Thumbs up
    "feedback_down": -4.0,        # Thumbs down
    "feedback_dismiss": -1.0,     # Dismissed
    "recency_boost": 1.5,         # Multiplier for recent watches
}

# Media domain definitions (from spec §3.3)
MEDIA_DOMAINS = {
    "movies": {"library_types": ["movie"], "section_keys": ["14", "20"]},
    "tv": {"library_types": ["show"], "section_keys": ["2", "7"]},
    "anime": {"library_types": ["show"], "section_keys": ["10", "15", "17"]},
}


class TasteProfiler:
    """Builds and manages user taste profiles from watch signals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_profile(
        self,
        user_id: int,
        depth_months: int = 12,
        domain: Optional[str] = None,
    ) -> dict:
        """Build complete taste profile for a user.

        Args:
            user_id: Database user ID
            depth_months: How far back to look (0 = all time)
            domain: "movies" | "tv" | "anime" | None (all domains)

        Returns:
            {
                "genre_affinities": {"Action": 0.85, "Horror": -0.3, ...},
                "personnel_affinities": {"Nolan": 0.9, "Spielberg": 0.7, ...},
                "keyword_affinities": {"time-travel": 0.8, ...},
                "anti_profile": {"genres": [...], "keywords": [...]},
                "stats": {"total_watches": N, "avg_completion": 0.78, ...},
                "embedding": [float, ...],  # aggregated taste vector
            }
        """
        # Get watch history with TMDB metadata
        since = None
        if depth_months > 0:
            since = datetime.now(timezone.utc) - timedelta(days=depth_months * 30)

        watches = await self._get_enriched_history(user_id, since, domain)

        if not watches:
            return self._empty_profile()

        # Get user feedback
        feedback = await self._get_feedback(user_id)

        # Get influence overrides
        overrides = await self._get_overrides(user_id)

        # Build affinity scores
        genre_scores = defaultdict(float)
        genre_counts = defaultdict(int)
        personnel_scores = defaultdict(float)
        keyword_scores = defaultdict(float)
        anti_genres = defaultdict(float)
        anti_keywords = defaultdict(float)

        total_signal = 0.0
        total_watches = len(watches)
        total_completion = 0.0

        for watch in watches:
            tmdb = watch["tmdb"]
            history = watch["history"]

            # Calculate signal strength for this watch
            signal = self._compute_signal(history, feedback.get(tmdb.tmdb_id, {}))
            decay = self._temporal_decay(history.started_at or history.created_at)
            weighted_signal = signal * decay

            total_signal += abs(weighted_signal)
            total_completion += float(history.completion_pct or 0)

            # Distribute signal across genres
            if tmdb.genres:
                genres = list(tmdb.genres.values()) if isinstance(tmdb.genres, dict) else tmdb.genres
                for genre in genres:
                    if weighted_signal > 0:
                        genre_scores[genre] += weighted_signal
                    else:
                        anti_genres[genre] += abs(weighted_signal)
                    genre_counts[genre] += 1

            # Distribute signal across keywords
            if tmdb.keywords:
                kw_list = tmdb.keywords if isinstance(tmdb.keywords, list) else list(tmdb.keywords)
                for kw in kw_list[:10]:
                    kw_str = str(kw)
                    if weighted_signal > 0:
                        keyword_scores[kw_str] += weighted_signal * 0.5
                    else:
                        anti_keywords[kw_str] += abs(weighted_signal) * 0.5

            # Distribute signal across personnel
            if tmdb.cast_crew:
                cc = tmdb.cast_crew if isinstance(tmdb.cast_crew, dict) else {}
                # Directors get full signal
                for crew in cc.get("crew", []):
                    if isinstance(crew, dict) and crew.get("job") == "Director":
                        personnel_scores[crew["name"]] += weighted_signal
                # Top-billed cast get partial signal
                for actor in cc.get("cast", [])[:3]:
                    if isinstance(actor, dict):
                        personnel_scores[actor["name"]] += weighted_signal * 0.3

        # Normalize scores to [-1, 1] range
        max_genre = max(genre_scores.values()) if genre_scores else 1.0
        max_genre = max(max_genre, max(anti_genres.values()) if anti_genres else 1.0, 1.0)

        genre_affinities = {}
        all_genres = set(genre_scores.keys()) | set(anti_genres.keys())
        for genre in all_genres:
            pos = genre_scores.get(genre, 0)
            neg = anti_genres.get(genre, 0)
            genre_affinities[genre] = round((pos - neg) / max_genre, 3)

        # Apply overrides
        for override in overrides:
            if override.influence_type == "genre" and override.influence_key in genre_affinities:
                if override.action == "boost":
                    genre_affinities[override.influence_key] = min(
                        1.0, genre_affinities[override.influence_key] + float(override.weight_modifier or 0.3)
                    )
                elif override.action == "suppress":
                    genre_affinities[override.influence_key] = max(
                        -1.0, genre_affinities[override.influence_key] - float(override.weight_modifier or 0.3)
                    )
                elif override.action == "block":
                    genre_affinities[override.influence_key] = -1.0

        # Normalize personnel
        max_pers = max(abs(v) for v in personnel_scores.values()) if personnel_scores else 1.0
        personnel_affinities = {
            k: round(v / max_pers, 3)
            for k, v in sorted(personnel_scores.items(), key=lambda x: abs(x[1]), reverse=True)[:50]
        }

        # Normalize keywords
        max_kw = max(abs(v) for v in keyword_scores.values()) if keyword_scores else 1.0
        keyword_affinities = {
            k: round(v / max_kw, 3)
            for k, v in sorted(keyword_scores.items(), key=lambda x: abs(x[1]), reverse=True)[:30]
        }

        # Anti-profile: genres and keywords consistently abandoned
        anti_profile = {
            "genres": [g for g, s in genre_affinities.items() if s < -0.3],
            "keywords": [
                k for k, v in sorted(anti_keywords.items(), key=lambda x: x[1], reverse=True)[:15]
                if v > 0
            ],
        }

        avg_completion = total_completion / total_watches if total_watches > 0 else 0

        return {
            "genre_affinities": dict(sorted(genre_affinities.items(), key=lambda x: x[1], reverse=True)),
            "personnel_affinities": personnel_affinities,
            "keyword_affinities": keyword_affinities,
            "anti_profile": anti_profile,
            "stats": {
                "total_watches": total_watches,
                "avg_completion": round(avg_completion, 1),
                "total_signal_strength": round(total_signal, 1),
                "domain": domain,
                "depth_months": depth_months,
            },
        }

    async def build_taste_embedding(
        self,
        user_id: int,
        domain: Optional[str] = None,
        depth_months: int = 12,
    ) -> list[float]:
        """Build a taste embedding by averaging embeddings of highly-rated watches.

        This creates a single vector representing the user's taste in embedding space,
        which can be directly compared against content embeddings via cosine similarity.
        """
        since = None
        if depth_months > 0:
            since = datetime.now(timezone.utc) - timedelta(days=depth_months * 30)

        watches = await self._get_enriched_history(user_id, since, domain)
        if not watches:
            return []

        feedback = await self._get_feedback(user_id)

        # Collect embeddings weighted by signal strength
        weighted_embeddings: list[tuple[list[float], float]] = []

        for watch in watches:
            tmdb = watch["tmdb"]
            history = watch["history"]

            if not tmdb.embedding_id:
                continue

            signal = self._compute_signal(history, feedback.get(tmdb.tmdb_id, {}))
            decay = self._temporal_decay(history.started_at or history.created_at)
            weight = signal * decay

            # Only include positive signals in taste vector
            if weight <= 0:
                continue

            # Get the embedding from ChromaDB
            # Note: actual embedding retrieval done by caller with EmbeddingService
            weighted_embeddings.append((tmdb.embedding_id, weight))

        return weighted_embeddings  # Caller resolves embedding_ids to vectors

    # ── Internal methods ─────────────────────────────────────────

    async def _get_enriched_history(
        self,
        user_id: int,
        since: Optional[datetime],
        domain: Optional[str],
    ) -> list[dict]:
        """Get watch history joined with TMDB metadata."""
        query = (
            select(WatchHistory, TmdbCache)
            .join(TmdbCache, and_(
                WatchHistory.tmdb_id == TmdbCache.tmdb_id,
                TmdbCache.media_type.in_(["movie", "show"]),
            ))
            .where(WatchHistory.user_id == user_id)
        )

        if since:
            query = query.where(WatchHistory.created_at >= since)

        if domain and domain in MEDIA_DOMAINS:
            # Filter by library access — domain maps to section keys
            section_keys = MEDIA_DOMAINS[domain]["section_keys"]
            accessible = await self.db.execute(
                select(UserLibraryAccess.plex_section_key).where(
                    and_(
                        UserLibraryAccess.user_id == user_id,
                        UserLibraryAccess.is_accessible == True,
                        UserLibraryAccess.plex_section_key.in_([int(k) for k in section_keys]),
                    )
                )
            )
            # We'll filter by TMDB media_type as a proxy for domain
            media_types = MEDIA_DOMAINS[domain]["library_types"]
            query = query.where(TmdbCache.media_type.in_(media_types))

        result = await self.db.execute(query)
        rows = result.all()

        return [{"history": row[0], "tmdb": row[1]} for row in rows]

    async def _get_feedback(self, user_id: int) -> dict[int, dict]:
        """Get all feedback keyed by tmdb_id."""
        result = await self.db.execute(
            select(Feedback).where(Feedback.user_id == user_id)
        )
        feedback = {}
        for fb in result.scalars():
            feedback[fb.tmdb_id] = {"type": fb.feedback}
        return feedback

    async def _get_overrides(self, user_id: int) -> list:
        """Get user's influence overrides."""
        result = await self.db.execute(
            select(InfluenceOverride).where(InfluenceOverride.user_id == user_id)
        )
        return list(result.scalars())

    def _compute_signal(self, history: WatchHistory, feedback: dict) -> float:
        """Compute signal strength for a single watch event."""
        signal = 0.0
        completion = float(history.completion_pct or 0)

        # Completion-based signal
        if completion >= 85:
            signal += SIGNAL_WEIGHTS["completion_full"]
        elif completion >= 40:
            signal += SIGNAL_WEIGHTS["completion_partial"]
        elif completion < 20 and completion > 0:
            signal += SIGNAL_WEIGHTS["completion_abandoned"]

        # Rewatch bonus
        if history.watch_count and history.watch_count > 1:
            signal += SIGNAL_WEIGHTS["rewatch"]

        # User rating
        if history.user_rating:
            rating = float(history.user_rating)
            if rating >= 8:
                signal += SIGNAL_WEIGHTS["user_rating_high"]
            elif rating <= 4:
                signal += SIGNAL_WEIGHTS["user_rating_low"]

        # Feedback
        fb_type = feedback.get("type")
        if fb_type == "up":
            signal += SIGNAL_WEIGHTS["feedback_up"]
        elif fb_type == "down":
            signal += SIGNAL_WEIGHTS["feedback_down"]
        elif fb_type == "dismiss":
            signal += SIGNAL_WEIGHTS["feedback_dismiss"]

        return signal

    def _temporal_decay(self, watched_at: Optional[datetime]) -> float:
        """Apply temporal decay — recent watches count more.

        Uses exponential decay with a half-life of 90 days.
        A watch from today has weight 1.0, 90 days ago = 0.5, 180 days = 0.25.
        """
        if not watched_at:
            return 0.5  # Unknown date gets half weight

        now = datetime.now(timezone.utc)
        if watched_at.tzinfo is None:
            watched_at = watched_at.replace(tzinfo=timezone.utc)

        days_ago = (now - watched_at).days
        half_life = 90  # days
        return math.exp(-0.693 * days_ago / half_life)  # ln(2) ≈ 0.693

    def _empty_profile(self) -> dict:
        """Return empty profile for users with no history."""
        return {
            "genre_affinities": {},
            "personnel_affinities": {},
            "keyword_affinities": {},
            "anti_profile": {"genres": [], "keywords": []},
            "stats": {
                "total_watches": 0,
                "avg_completion": 0,
                "total_signal_strength": 0,
                "domain": None,
                "depth_months": 0,
            },
        }
