"""TMDB metadata sync service.

Fetches rich metadata from TMDB for all Plex library items,
caches it in PostgreSQL, and prepares text for embedding.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.clients.tmdb import TmdbClient
from app.clients.plex import PlexClient
from app.models.tables import TmdbCache

logger = logging.getLogger(__name__)


class TmdbSyncService:
    """Syncs TMDB metadata for all Plex library items into local cache."""

    # TMDB rate limit: 40 req/s. We stay conservative.
    RATE_LIMIT_DELAY = 0.05  # 20 req/s effective
    BATCH_SIZE = 50

    def __init__(self, tmdb: TmdbClient, plex: PlexClient, db: AsyncSession):
        self.tmdb = tmdb
        self.plex = plex
        self.db = db

    async def sync_library(
        self,
        library_id: str,
        force_refresh: bool = False,
        cache_ttl_days: int = 7,
        progress_callback=None,
    ) -> dict:
        """Sync all items from a Plex library with TMDB metadata.

        Args:
            library_id: Plex library section key
            force_refresh: Re-fetch even if cached
            cache_ttl_days: How long cache entries are valid
            progress_callback: async fn(current, total, title) for progress reporting

        Returns:
            {"synced": N, "skipped": N, "failed": N, "total": N}
        """
        # Step 1: Get GUID map from Plex (rating_key → tmdb_id)
        guid_map = await self.plex.get_all_library_guids(library_id)
        libs = await self.plex.get_libraries()
        lib = next((l for l in libs if l.id == library_id), None)
        lib_type = lib.type if lib else "movie"
        media_type = "movie" if lib_type == "movie" else "show"

        total = len(guid_map)
        synced = 0
        skipped = 0
        failed = 0

        # Step 2: Filter to items needing sync
        cutoff = datetime.now(timezone.utc) - timedelta(days=cache_ttl_days)
        to_fetch: list[tuple[str, int]] = []  # (rating_key, tmdb_id)

        for rating_key, tmdb_raw in guid_map.items():
            # Skip IMDB-only items for now (need resolution)
            if isinstance(tmdb_raw, str) and tmdb_raw.startswith("imdb"):
                failed += 1
                continue

            try:
                tmdb_id = int(tmdb_raw)
            except (ValueError, TypeError):
                failed += 1
                continue

            if not force_refresh:
                # Check cache freshness
                cached = await self.db.execute(
                    select(TmdbCache.fetched_at).where(
                        and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                    )
                )
                row = cached.scalar_one_or_none()
                if row and row > cutoff:
                    skipped += 1
                    continue

            to_fetch.append((rating_key, tmdb_id))

        logger.info(f"Library {library_id}: {len(to_fetch)} to fetch, {skipped} cached, {failed} unresolvable")

        # Step 3: Fetch from TMDB in batches with rate limiting
        for i, (rating_key, tmdb_id) in enumerate(to_fetch):
            try:
                if media_type == "movie":
                    data = await self.tmdb.get_movie(tmdb_id)
                else:
                    data = await self.tmdb.get_show(tmdb_id)

                await self._upsert_cache(data)
                synced += 1

                if progress_callback:
                    await progress_callback(i + 1, len(to_fetch), data.get("title", "?"))

            except Exception as e:
                logger.warning(f"TMDB fetch failed for tmdb_id={tmdb_id}: {e}")
                failed += 1

            # Rate limiting
            await asyncio.sleep(self.RATE_LIMIT_DELAY)

            # Commit in batches to avoid holding transaction too long
            if (i + 1) % self.BATCH_SIZE == 0:
                await self.db.commit()

        await self.db.commit()

        return {
            "synced": synced,
            "skipped": skipped,
            "failed": failed,
            "total": total,
        }

    async def sync_single(self, tmdb_id: int, media_type: str = "movie") -> Optional[dict]:
        """Fetch and cache a single item. Returns normalized metadata."""
        try:
            if media_type == "movie":
                data = await self.tmdb.get_movie(tmdb_id)
            else:
                data = await self.tmdb.get_show(tmdb_id)

            await self._upsert_cache(data)
            await self.db.commit()
            return data
        except Exception as e:
            logger.warning(f"TMDB sync failed for {tmdb_id}: {e}")
            return None

    async def get_cached(self, tmdb_id: int, media_type: str = "movie") -> Optional[TmdbCache]:
        """Get cached TMDB metadata, fetching if missing."""
        result = await self.db.execute(
            select(TmdbCache).where(
                and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row

        # Cache miss — fetch from TMDB
        data = await self.sync_single(tmdb_id, media_type)
        if data:
            result = await self.db.execute(
                select(TmdbCache).where(
                    and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                )
            )
            return result.scalar_one_or_none()
        return None

    def build_embedding_text(self, cache: TmdbCache) -> str:
        """Build rich text representation for embedding.

        Combines title, genres, keywords, cast, crew, overview, and
        production context into a single text optimized for
        semantic similarity search.
        """
        parts = []

        # Title + year
        title = cache.title or ""
        year = f"({cache.year})" if cache.year else ""
        parts.append(f"{title} {year}".strip())

        # Genres
        if cache.genres:
            genre_names = list(cache.genres.values()) if isinstance(cache.genres, dict) else cache.genres
            parts.append(f"Genres: {', '.join(str(g) for g in genre_names)}")

        # Keywords (thematic DNA)
        if cache.keywords:
            kw_list = cache.keywords if isinstance(cache.keywords, list) else list(cache.keywords)
            parts.append(f"Themes: {', '.join(str(k) for k in kw_list[:15])}")

        # Cast + crew
        if cache.cast_crew:
            cc = cache.cast_crew if isinstance(cache.cast_crew, dict) else {}
            cast = cc.get("cast", [])
            crew = cc.get("crew", [])
            if cast:
                actor_names = [c["name"] for c in cast[:5] if isinstance(c, dict)]
                parts.append(f"Cast: {', '.join(actor_names)}")
            if crew:
                crew_names = [f"{c['name']} ({c['job']})" for c in crew if isinstance(c, dict)]
                parts.append(f"Crew: {', '.join(crew_names)}")

        # Overview (plot summary — strong semantic signal)
        if cache.overview:
            parts.append(cache.overview)

        # Production context
        if cache.original_language and cache.original_language != "en":
            parts.append(f"Language: {cache.original_language}")
        if cache.production_countries:
            countries = cache.production_countries if isinstance(cache.production_countries, list) else []
            if countries:
                parts.append(f"Country: {', '.join(str(c) for c in countries)}")

        return " | ".join(parts)

    async def _upsert_cache(self, data: dict) -> None:
        """Insert or update TMDB cache entry."""
        stmt = pg_insert(TmdbCache).values(
            tmdb_id=data["tmdb_id"],
            media_type=data["media_type"],
            title=data.get("title"),
            original_title=data.get("original_title"),
            year=data.get("year"),
            genres=data.get("genres"),
            keywords=data.get("keywords"),
            cast_crew=data.get("cast_crew"),
            overview=data.get("overview"),
            vote_average=data.get("vote_average"),
            popularity=data.get("popularity"),
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            trailer_key=data.get("trailer_key"),
            runtime_minutes=data.get("runtime_minutes"),
            original_language=data.get("original_language"),
            production_countries=data.get("production_countries"),
            similar_ids=data.get("similar_ids"),
            fetched_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["tmdb_id", "media_type"],
            set_={
                "title": data.get("title"),
                "original_title": data.get("original_title"),
                "year": data.get("year"),
                "genres": data.get("genres"),
                "keywords": data.get("keywords"),
                "cast_crew": data.get("cast_crew"),
                "overview": data.get("overview"),
                "vote_average": data.get("vote_average"),
                "popularity": data.get("popularity"),
                "poster_path": data.get("poster_path"),
                "backdrop_path": data.get("backdrop_path"),
                "trailer_key": data.get("trailer_key"),
                "runtime_minutes": data.get("runtime_minutes"),
                "original_language": data.get("original_language"),
                "production_countries": data.get("production_countries"),
                "similar_ids": data.get("similar_ids"),
                "fetched_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)
