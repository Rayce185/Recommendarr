"""Servarr-first metadata sync — pulls from all registered instances.

Syncs from Radarr/Sonarr (instant, local, no rate limits) into the
tmdb_cache table. Uses the instance registry to iterate all configured
instances dynamically — no hardcoded instance names.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient
from app.clients.servarr_models import ServarrMovie, ServarrSeries
from app.models.tables import TmdbCache

logger = logging.getLogger(__name__)


class ServarrSyncService:
    """Syncs metadata from all registered Radarr/Sonarr instances."""

    def __init__(self, registry):
        """Args: registry — InstanceRegistry from factory."""
        self.registry = registry

    async def sync_movies(self, db, instance_name: str, client: RadarrClient,
                          progress_callback=None) -> dict:
        """Pull all movies from a single Radarr instance into tmdb_cache."""
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        movies = await client.get_all_movies()
        inserted = 0

        for i, m in enumerate(movies):
            genres_str = str(m.genres) if m.genres else "[]"
            try:
                existing = db.execute(
                    select(TmdbCache).where(
                        TmdbCache.tmdb_id == m.tmdb_id,
                        TmdbCache.media_type == "movie",
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.title = m.title
                    existing.original_title = m.original_title
                    existing.year = m.year
                    existing.overview = m.overview
                    existing.vote_average = m.vote_average
                    existing.popularity = m.popularity
                    existing.poster_path = m.poster_path
                    existing.runtime_minutes = m.runtime_minutes
                    existing.original_language = m.original_language
                else:
                    db.add(TmdbCache(
                        tmdb_id=m.tmdb_id, media_type="movie",
                        title=m.title, original_title=m.original_title,
                        year=m.year, overview=m.overview,
                        vote_average=m.vote_average, popularity=m.popularity,
                        poster_path=m.poster_path,
                        runtime_minutes=m.runtime_minutes,
                        original_language=m.original_language,
                    ))
                inserted += 1

                if (i + 1) % 500 == 0:
                    db.commit()
                    if progress_callback:
                        await progress_callback(i + 1, len(movies), m.title)
            except Exception as e:
                logger.debug(f"Sync skip movie {m.tmdb_id}: {e}")

        db.commit()
        return {"inserted": inserted, "total": len(movies), "source": instance_name}

    async def sync_series(self, db, instance_name: str, client: SonarrClient,
                          progress_callback=None) -> dict:
        """Pull all series from a single Sonarr instance into tmdb_cache."""
        series_list = await client.get_all_series()
        inserted = 0
        skipped = 0

        for i, s in enumerate(series_list):
            if not s.tmdb_id:
                skipped += 1
                continue

            try:
                existing = db.execute(
                    select(TmdbCache).where(
                        TmdbCache.tmdb_id == s.tmdb_id,
                        TmdbCache.media_type == "show",
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.title = s.title
                    existing.year = s.year
                    existing.overview = s.overview
                    existing.vote_average = s.vote_average
                    existing.runtime_minutes = s.runtime_minutes
                    existing.original_language = s.original_language
                    existing.poster_path = s.poster_path
                else:
                    db.add(TmdbCache(
                        tmdb_id=s.tmdb_id, media_type="show",
                        title=s.title, year=s.year,
                        overview=s.overview, vote_average=s.vote_average,
                        runtime_minutes=s.runtime_minutes,
                        original_language=s.original_language,
                        poster_path=s.poster_path,
                    ))
                inserted += 1

                if (i + 1) % 200 == 0:
                    db.commit()
                    if progress_callback:
                        await progress_callback(i + 1, len(series_list), s.title)
            except Exception as e:
                logger.debug(f"Sync skip series {s.tmdb_id}: {e}")

        db.commit()
        return {"inserted": inserted, "skipped": skipped,
                "total": len(series_list), "source": instance_name}

    async def sync_all(self, db, progress_callback=None) -> dict:
        """Sync from ALL registered instances — Radarr and Sonarr."""
        results = {}
        t0 = time.time()

        # Sync all Radarr instances
        for name, client in self.registry.get_by_type("radarr"):
            try:
                results[name] = await self.sync_movies(
                    db, name, client, progress_callback)
            except Exception as e:
                results[name] = {"error": str(e), "source": name}
                logger.error(f"Sync failed for {name}: {e}")

        # Sync all Sonarr instances
        for name, client in self.registry.get_by_type("sonarr"):
            try:
                results[name] = await self.sync_series(
                    db, name, client, progress_callback)
            except Exception as e:
                results[name] = {"error": str(e), "source": name}
                logger.error(f"Sync failed for {name}: {e}")

        results["elapsed_seconds"] = round(time.time() - t0, 1)

        # Total in DB
        from app.database import get_db
        try:
            with get_db() as session:
                count = session.execute(
                    select(func.count()).select_from(TmdbCache)
                ).scalar()
                results["total_cached"] = count
        except Exception:
            pass

        return results
