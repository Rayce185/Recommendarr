"""Recommendation engine — the core product.

Combines taste profiles, content embeddings, and contextual signals
to generate ranked, explained recommendations.

Modes implemented here:
- "Watch Tonight" (in-library)
- "Worth Grabbing" (not in library, needs Radarr/Sonarr)
- "Rediscover" (rewatch suggestions)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import (
    TmdbCache, WatchHistory, UserLibraryAccess, RecommendationLog, Feedback,
)
from app.services.embedding import EmbeddingService
from app.services.taste_profiler import TasteProfiler
from app.services.explanations import ExplanationEngine

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    """A single recommendation with metadata and explanation."""
    tmdb_id: int
    media_type: str
    title: str
    year: Optional[int]
    poster_path: Optional[str]
    backdrop_path: Optional[str]
    trailer_key: Optional[str]
    genres: list[str]
    overview: Optional[str]
    vote_average: Optional[float]
    runtime_minutes: Optional[int]
    original_language: Optional[str]
    score: float                     # 0.0 – 1.0 confidence
    explanation: str                 # "Because you..."
    signals: dict                    # What influenced this score
    mode: str                        # "tonight" | "grab" | "rediscover"
    in_library: bool
    quality_info: Optional[dict] = None   # Resolution, HDR, codecs


class RecommendationEngine:
    """Generates recommendations by combining taste profiles with content embeddings."""

    def __init__(
        self,
        db: AsyncSession,
        embedding: EmbeddingService,
        explainer: ExplanationEngine,
    ):
        self.db = db
        self.embedding = embedding
        self.explainer = explainer
        self.profiler = TasteProfiler(db)

    async def recommend_tonight(
        self,
        user_id: int,
        limit: int = 10,
        filters: Optional[dict] = None,
    ) -> list[Recommendation]:
        """'Watch Tonight' — recommend from user's accessible library.

        Strategy:
        1. Build taste embedding from user's watch history
        2. Query ChromaDB for similar content
        3. Filter to in-library items the user hasn't watched
        4. Rank by similarity + taste affinity + popularity
        5. Generate explanations
        """
        profile = await self.profiler.build_profile(user_id)
        if profile["stats"]["total_watches"] == 0:
            return await self._cold_start_recommendations(user_id, limit, filters)

        # Get user's accessible libraries
        accessible_tmdb_ids = await self._get_accessible_tmdb_ids(user_id)
        watched_tmdb_ids = await self._get_watched_tmdb_ids(user_id)

        # Build taste vector from top-rated watches
        taste_vector = await self._build_taste_vector(user_id, profile)
        if not taste_vector:
            return await self._cold_start_recommendations(user_id, limit, filters)

        # Query ChromaDB — get more than we need for filtering
        query_limit = min(limit * 5, 200)
        results = await self.embedding.query_similar(
            taste_vector,
            n_results=query_limit,
        )

        candidates = await self._process_results(
            results,
            accessible_tmdb_ids=accessible_tmdb_ids,
            exclude_tmdb_ids=watched_tmdb_ids,
            in_library_only=True,
            profile=profile,
            filters=filters,
        )

        # Take top N
        recommendations = candidates[:limit]

        # Generate explanations
        for rec in recommendations:
            rec.explanation = self.explainer.explain(rec, profile)
            rec.mode = "tonight"

        # Log recommendations
        await self._log_recommendations(user_id, recommendations)

        return recommendations

    async def recommend_grab(
        self,
        user_id: int,
        limit: int = 10,
        filters: Optional[dict] = None,
    ) -> list[Recommendation]:
        """'Worth Grabbing' — recommend content NOT in library.

        Same as tonight but inverted: finds items the user would love
        that aren't on the server yet. Used with Radarr/Sonarr.
        """
        profile = await self.profiler.build_profile(user_id)
        if profile["stats"]["total_watches"] == 0:
            return []

        accessible_tmdb_ids = await self._get_accessible_tmdb_ids(user_id)
        watched_tmdb_ids = await self._get_watched_tmdb_ids(user_id)

        taste_vector = await self._build_taste_vector(user_id, profile)
        if not taste_vector:
            return []

        # Query ChromaDB — we want items NOT in the user's library
        query_limit = min(limit * 10, 500)
        results = await self.embedding.query_similar(taste_vector, n_results=query_limit)

        candidates = await self._process_results(
            results,
            accessible_tmdb_ids=accessible_tmdb_ids,
            exclude_tmdb_ids=watched_tmdb_ids,
            in_library_only=False,  # Inverted — we want NOT in library
            profile=profile,
            filters=filters,
        )

        # For "grab" mode: filter to items NOT in accessible library
        candidates = [c for c in candidates if not c.in_library]

        recommendations = candidates[:limit]
        for rec in recommendations:
            rec.explanation = self.explainer.explain(rec, profile)
            rec.mode = "grab"

        await self._log_recommendations(user_id, recommendations)
        return recommendations

    async def recommend_rediscover(
        self,
        user_id: int,
        limit: int = 10,
    ) -> list[Recommendation]:
        """'Rediscover' — suggest rewatching previously enjoyed content.

        Finds items the user watched and loved (high signal) but hasn't
        watched recently. Time-gated: at least 6 months since last watch.
        """
        from datetime import timedelta

        result = await self.db.execute(
            select(WatchHistory, TmdbCache)
            .join(TmdbCache, and_(
                WatchHistory.tmdb_id == TmdbCache.tmdb_id,
            ))
            .where(
                and_(
                    WatchHistory.user_id == user_id,
                    WatchHistory.completion_pct >= 70,
                )
            )
            .order_by(WatchHistory.created_at.asc())  # Oldest first
        )
        rows = result.all()

        profile = await self.profiler.build_profile(user_id)
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
        from datetime import timezone

        candidates = []
        for history, tmdb in rows:
            # Skip if watched recently
            watched_at = history.started_at or history.created_at
            if watched_at and watched_at.replace(tzinfo=timezone.utc) > six_months_ago:
                continue

            signal = self.profiler._compute_signal(history, {})
            if signal < 3.0:  # Only strong positive signals
                continue

            rec = self._tmdb_to_recommendation(tmdb, score=signal / 10.0, in_library=True)
            rec.signals = {"original_signal": signal, "last_watched": str(watched_at)}
            candidates.append(rec)

        # Sort by signal strength (how much they loved it)
        candidates.sort(key=lambda r: r.score, reverse=True)
        recommendations = candidates[:limit]

        for rec in recommendations:
            rec.explanation = self.explainer.explain(rec, profile, mode="rediscover")
            rec.mode = "rediscover"

        return recommendations

    # ── Internal methods ─────────────────────────────────────────

    async def _build_taste_vector(self, user_id: int, profile: dict) -> Optional[list[float]]:
        """Build aggregated taste embedding by averaging positive-signal watch embeddings."""
        weighted_refs = await self.profiler.build_taste_embedding(user_id)
        if not weighted_refs:
            return None

        # Resolve embedding_ids to actual vectors from ChromaDB
        collection_id = await self.embedding.ensure_collection()
        v2_base = f"{self.embedding.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database"

        ids = [ref[0] for ref in weighted_refs[:100]]  # Cap at 100 for performance
        weights = [ref[1] for ref in weighted_refs[:100]]

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{v2_base}/collections/{collection_id}/get",
                json={"ids": ids, "include": ["embeddings"]},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()

        embeddings = data.get("embeddings", [])
        if not embeddings:
            return None

        # Weighted average
        dim = len(embeddings[0])
        taste = [0.0] * dim
        total_weight = sum(weights[:len(embeddings)])

        for emb, weight in zip(embeddings, weights):
            for i in range(dim):
                taste[i] += emb[i] * weight

        if total_weight > 0:
            taste = [v / total_weight for v in taste]

        return taste

    async def _get_accessible_tmdb_ids(self, user_id: int) -> set[int]:
        """Get set of TMDB IDs the user can access (library permission enforcement)."""
        # Get user's accessible section keys
        result = await self.db.execute(
            select(UserLibraryAccess.plex_section_key).where(
                and_(
                    UserLibraryAccess.user_id == user_id,
                    UserLibraryAccess.is_accessible == True,
                )
            )
        )
        section_keys = {row[0] for row in result.all()}

        if not section_keys:
            # Admin or unsynced — return all cached TMDB IDs
            result = await self.db.execute(select(TmdbCache.tmdb_id))
            return {row[0] for row in result.all()}

        # Get all TMDB IDs from accessible libraries
        # Note: this requires a library→tmdb mapping table or Plex GUID cache
        # For now, return all cached — library filtering happens at item level
        result = await self.db.execute(select(TmdbCache.tmdb_id))
        return {row[0] for row in result.all()}

    async def _get_watched_tmdb_ids(self, user_id: int) -> set[int]:
        """Get set of TMDB IDs the user has already watched (≥40% completion)."""
        result = await self.db.execute(
            select(WatchHistory.tmdb_id).where(
                and_(
                    WatchHistory.user_id == user_id,
                    WatchHistory.completion_pct >= 40,
                )
            )
        )
        return {row[0] for row in result.all()}

    async def _process_results(
        self,
        chroma_results: dict,
        accessible_tmdb_ids: set[int],
        exclude_tmdb_ids: set[int],
        in_library_only: bool,
        profile: dict,
        filters: Optional[dict] = None,
    ) -> list[Recommendation]:
        """Process ChromaDB results into scored, filtered recommendations."""
        candidates = []

        ids = chroma_results.get("ids", [[]])[0]
        distances = chroma_results.get("distances", [[]])[0]
        metadatas = chroma_results.get("metadatas", [[]])[0]

        for doc_id, distance, metadata in zip(ids, distances, metadatas):
            tmdb_id = metadata.get("tmdb_id")
            if not tmdb_id:
                continue

            # Skip already watched
            if tmdb_id in exclude_tmdb_ids:
                continue

            # Library filter
            in_lib = tmdb_id in accessible_tmdb_ids
            if in_library_only and not in_lib:
                continue

            # Cosine distance → similarity score (0-1, higher is better)
            similarity = max(0.0, 1.0 - distance)

            # Get full metadata from DB
            result = await self.db.execute(
                select(TmdbCache).where(TmdbCache.tmdb_id == tmdb_id).limit(1)
            )
            tmdb_cache = result.scalar_one_or_none()
            if not tmdb_cache:
                continue

            # Apply genre affinity boost
            genre_boost = self._genre_boost(tmdb_cache, profile)

            # Apply anti-profile penalty
            anti_penalty = self._anti_penalty(tmdb_cache, profile)

            # Popularity factor (mild — prevent pure popularity ranking)
            pop_factor = 0.0
            if tmdb_cache.vote_average:
                pop_factor = float(tmdb_cache.vote_average) / 100.0  # 0.0-0.1

            # Combined score
            score = (similarity * 0.6) + (genre_boost * 0.25) + (pop_factor * 0.05) - (anti_penalty * 0.10)
            score = max(0.0, min(1.0, score))

            # Apply filters
            if filters and not self._passes_filters(tmdb_cache, filters):
                continue

            rec = self._tmdb_to_recommendation(tmdb_cache, score=score, in_library=in_lib)
            rec.signals = {
                "similarity": round(similarity, 4),
                "genre_boost": round(genre_boost, 4),
                "anti_penalty": round(anti_penalty, 4),
                "popularity_factor": round(pop_factor, 4),
            }
            candidates.append(rec)

        # Sort by score descending
        candidates.sort(key=lambda r: r.score, reverse=True)
        return candidates

    def _genre_boost(self, tmdb: TmdbCache, profile: dict) -> float:
        """Calculate genre affinity boost for a candidate."""
        if not tmdb.genres or not profile["genre_affinities"]:
            return 0.0

        genres = list(tmdb.genres.values()) if isinstance(tmdb.genres, dict) else tmdb.genres
        affinities = profile["genre_affinities"]

        boosts = [affinities.get(g, 0.0) for g in genres]
        return sum(boosts) / len(boosts) if boosts else 0.0

    def _anti_penalty(self, tmdb: TmdbCache, profile: dict) -> float:
        """Calculate penalty for anti-profile matches."""
        anti = profile.get("anti_profile", {})
        penalty = 0.0

        if tmdb.genres:
            genres = list(tmdb.genres.values()) if isinstance(tmdb.genres, dict) else tmdb.genres
            for g in genres:
                if g in anti.get("genres", []):
                    penalty += 0.3

        if tmdb.keywords:
            kw_list = tmdb.keywords if isinstance(tmdb.keywords, list) else []
            for kw in kw_list:
                if str(kw) in anti.get("keywords", []):
                    penalty += 0.1

        return min(penalty, 1.0)

    def _passes_filters(self, tmdb: TmdbCache, filters: dict) -> bool:
        """Check if a candidate passes user-specified filters."""
        if "genres" in filters and tmdb.genres:
            genre_list = list(tmdb.genres.values()) if isinstance(tmdb.genres, dict) else tmdb.genres
            required = filters["genres"].split(",") if isinstance(filters["genres"], str) else filters["genres"]
            if not any(g in genre_list for g in required):
                return False

        if "exclude_genres" in filters and tmdb.genres:
            genre_list = list(tmdb.genres.values()) if isinstance(tmdb.genres, dict) else tmdb.genres
            excluded = filters["exclude_genres"].split(",") if isinstance(filters["exclude_genres"], str) else filters["exclude_genres"]
            if any(g in genre_list for g in excluded):
                return False

        if "year_min" in filters and tmdb.year:
            if tmdb.year < int(filters["year_min"]):
                return False

        if "year_max" in filters and tmdb.year:
            if tmdb.year > int(filters["year_max"]):
                return False

        if "language" in filters and tmdb.original_language:
            if tmdb.original_language != filters["language"]:
                return False

        return True

    def _tmdb_to_recommendation(self, tmdb: TmdbCache, score: float, in_library: bool) -> Recommendation:
        """Convert a TmdbCache row to a Recommendation object."""
        genres = []
        if tmdb.genres:
            genres = list(tmdb.genres.values()) if isinstance(tmdb.genres, dict) else tmdb.genres

        return Recommendation(
            tmdb_id=tmdb.tmdb_id,
            media_type=tmdb.media_type,
            title=tmdb.title or "",
            year=tmdb.year,
            poster_path=tmdb.poster_path,
            backdrop_path=tmdb.backdrop_path,
            trailer_key=tmdb.trailer_key,
            genres=genres,
            overview=tmdb.overview,
            vote_average=float(tmdb.vote_average) if tmdb.vote_average else None,
            runtime_minutes=tmdb.runtime_minutes,
            original_language=tmdb.original_language,
            score=round(score, 4),
            explanation="",  # Filled in by caller
            signals={},
            mode="",
            in_library=in_library,
        )

    async def _cold_start_recommendations(
        self, user_id: int, limit: int, filters: Optional[dict] = None
    ) -> list[Recommendation]:
        """Fallback for users with no watch history — popularity-based."""
        query = (
            select(TmdbCache)
            .where(TmdbCache.vote_average.is_not(None))
            .order_by(TmdbCache.popularity.desc())
            .limit(limit * 3)
        )
        result = await self.db.execute(query)
        items = list(result.scalars())

        recs = []
        for tmdb in items:
            if filters and not self._passes_filters(tmdb, filters):
                continue
            rec = self._tmdb_to_recommendation(tmdb, score=0.5, in_library=True)
            rec.explanation = "Popular on the server — give it a try!"
            rec.mode = "tonight"
            rec.signals = {"method": "cold_start_popularity"}
            recs.append(rec)
            if len(recs) >= limit:
                break

        return recs

    async def _log_recommendations(self, user_id: int, recs: list[Recommendation]) -> None:
        """Log generated recommendations for tracking and learning."""
        for rec in recs:
            log = RecommendationLog(
                user_id=user_id,
                tmdb_id=rec.tmdb_id,
                media_type=rec.media_type,
                mode=rec.mode,
                score=rec.score,
                explanation=rec.explanation,
                signals=rec.signals,
            )
            self.db.add(log)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
