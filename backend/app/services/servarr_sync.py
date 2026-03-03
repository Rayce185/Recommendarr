"""Servarr-first metadata sync — replaces TMDB bulk pull.

Pulls from Radarr/Sonarr (instant, local, no rate limits),
caches in tmdb_cache table, embeds into ChromaDB.
TMDB API only used for enrichment (cast/crew, keywords) on demand.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func

from app.clients.servarr import RadarrClient, SonarrClient, ServarrMovie, ServarrSeries
from app.models.tables import TmdbCache

logger = logging.getLogger(__name__)


class ServarrSyncService:
    """Syncs metadata from Radarr/Sonarr into local cache."""

    def __init__(self, radarr: RadarrClient, sonarr_tv: SonarrClient = None,
                 sonarr_anime: SonarrClient = None):
        self.radarr = radarr
        self.sonarr_tv = sonarr_tv
        self.sonarr_anime = sonarr_anime

    async def sync_movies(self, db: AsyncSession, progress_callback=None) -> dict:
        """Pull all movies from Radarr into tmdb_cache."""
        movies = await self.radarr.get_all_movies()
        inserted = 0
        updated = 0
        skipped = 0

        for i, m in enumerate(movies):
            genres_dict = {g: g for g in m.genres} if m.genres else {}

            stmt = pg_insert(TmdbCache).values(
                tmdb_id=m.tmdb_id,
                media_type="movie",
                title=m.title,
                original_title=m.original_title,
                year=m.year,
                genres=genres_dict,
                overview=m.overview,
                vote_average=m.vote_average,
                popularity=m.popularity,
                poster_path=m.poster_path,
                runtime_minutes=m.runtime_minutes,
                original_language=m.original_language,
                fetched_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["tmdb_id", "media_type"],
                set_={
                    "title": m.title,
                    "original_title": m.original_title,
                    "year": m.year,
                    "genres": genres_dict,
                    "overview": m.overview,
                    "vote_average": m.vote_average,
                    "popularity": m.popularity,
                    "poster_path": m.poster_path,
                    "runtime_minutes": m.runtime_minutes,
                    "original_language": m.original_language,
                    "fetched_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)

            if (i + 1) % 500 == 0:
                await db.commit()
                if progress_callback:
                    await progress_callback(i + 1, len(movies), m.title)

            inserted += 1

        await db.commit()
        return {"inserted": inserted, "total": len(movies), "source": "radarr"}

    async def sync_series(self, db: AsyncSession, source: str = "tv",
                          progress_callback=None) -> dict:
        """Pull all series from Sonarr into tmdb_cache."""
        client = self.sonarr_tv if source == "tv" else self.sonarr_anime
        if not client:
            return {"inserted": 0, "total": 0, "source": f"sonarr-{source}", "error": "no client"}

        series_list = await client.get_all_series()
        inserted = 0
        skipped = 0

        for i, s in enumerate(series_list):
            if not s.tmdb_id:
                skipped += 1
                continue

            genres_dict = {g: g for g in s.genres} if s.genres else {}

            stmt = pg_insert(TmdbCache).values(
                tmdb_id=s.tmdb_id,
                media_type="show",
                title=s.title,
                year=s.year,
                genres=genres_dict,
                overview=s.overview,
                vote_average=s.vote_average,
                runtime_minutes=s.runtime_minutes,
                original_language=s.original_language,
                poster_path=s.poster_path,
                fetched_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["tmdb_id", "media_type"],
                set_={
                    "title": s.title,
                    "year": s.year,
                    "genres": genres_dict,
                    "overview": s.overview,
                    "vote_average": s.vote_average,
                    "runtime_minutes": s.runtime_minutes,
                    "original_language": s.original_language,
                    "poster_path": s.poster_path,
                    "fetched_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)
            inserted += 1

            if (i + 1) % 200 == 0:
                await db.commit()
                if progress_callback:
                    await progress_callback(i + 1, len(series_list), s.title)

        await db.commit()
        return {"inserted": inserted, "skipped": skipped,
                "total": len(series_list), "source": f"sonarr-{source}"}

    async def sync_all(self, db: AsyncSession, progress_callback=None) -> dict:
        """Sync everything: Radarr movies + both Sonarr instances."""
        results = {}

        t0 = time.time()
        results["movies"] = await self.sync_movies(db, progress_callback)
        results["tv"] = await self.sync_series(db, "tv", progress_callback)
        results["anime"] = await self.sync_series(db, "anime", progress_callback)
        results["elapsed_seconds"] = round(time.time() - t0, 1)

        # Get total in DB
        count = await db.execute(select(func.count(TmdbCache.tmdb_id)))
        results["total_cached"] = count.scalar()

        return results
