"""Collection completion service — finds partially watched franchises.

Uses a 3-tier caching strategy:
  L1: In-memory dict (_movie_coll, _coll_cache) — fastest, lost on restart
  L2: Database tables (movie_collection_map, collection_details,
      collection_results_cache) — survives restarts, serves stale-while-revalidate
  L3: TMDB API — source of truth, slowest
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from app.database import get_db, is_postgres
from app.models.features import (
    MovieCollectionMap, CollectionDetail, CollectionResultsCache,
)

logger = logging.getLogger(__name__)

RESULTS_TTL = 21600  # 6 hours — after this, background refresh triggers



@dataclass
class CollectionPart:
    tmdb_id: int
    title: str
    year: int | None
    poster_url: str | None
    vote_average: float
    in_library: bool
    watched: bool
    release_date: str | None = None


@dataclass
class UserCollection:
    collection_id: int
    name: str
    poster_url: str | None
    backdrop_url: str | None
    total_parts: int
    watched_count: int
    in_library_count: int
    completion_pct: float
    parts: list[CollectionPart] = field(default_factory=list)
    missing_parts: list[CollectionPart] = field(default_factory=list)


class CollectionService:
    """Finds partially watched franchises for a user."""

    def __init__(self, tmdb, radarr, tautulli):
        self.tmdb = tmdb
        self.radarr = radarr
        self.tautulli = tautulli
        self._movie_coll: dict[int, int | None] = {}
        self._coll_cache: dict[int, dict] = {}
        self._load_persistent_caches()

    def _load_persistent_caches(self):
        """Load L2 caches into L1 memory on startup."""
        try:
            with get_db() as db:
                rows = db.execute(select(MovieCollectionMap)).scalars().all()
                for row in rows:
                    self._movie_coll[row.tmdb_id] = row.collection_id

                rows = db.execute(select(CollectionDetail)).scalars().all()
                for row in rows:
                    data = row.data if isinstance(row.data, dict) else json.loads(row.data)
                    self._coll_cache[row.collection_id] = data

            if self._movie_coll:
                logger.info(
                    f"Loaded {len(self._movie_coll)} movie→collection + "
                    f"{len(self._coll_cache)} collection details from DB"
                )
        except Exception as e:
            logger.warning(f"Could not load collection caches: {e}")

    # ── DB persistence helpers ────────────────────────────────────

    def _persist_movie_coll_batch(self, mappings: list[tuple[int, int | None]]):
        """Batch-save movie→collection mappings."""
        if not mappings:
            return
        try:
            with get_db() as db:
                for tmdb_id, coll_id in mappings:
                    existing = db.get(MovieCollectionMap, tmdb_id)
                    if existing:
                        existing.collection_id = coll_id
                    else:
                        db.add(MovieCollectionMap(
                            tmdb_id=tmdb_id, collection_id=coll_id
                        ))
                db.commit()
        except Exception:
            pass

    def _persist_coll_detail(self, coll_id: int, data: dict):
        """Save a collection's detail data to DB."""
        try:
            with get_db() as db:
                existing = db.get(CollectionDetail, coll_id)
                if existing:
                    existing.data = data
                    existing.fetched_at = time.time()
                else:
                    db.add(CollectionDetail(
                        collection_id=coll_id, data=data, fetched_at=time.time()
                    ))
                db.commit()
        except Exception:
            pass

    def get_cached_results(self, username: str) -> tuple[list[dict] | None, bool]:
        """Return (cached_results, is_fresh) from L2 cache.

        Returns (None, False) if no cached data exists.
        Returns (data, True) if data exists and is within TTL.
        Returns (data, False) if data exists but is stale.
        """
        try:
            with get_db() as db:
                row = db.get(CollectionResultsCache, username)
                if row:
                    data = row.data if isinstance(row.data, dict) else json.loads(row.data)
                    age = time.time() - float(row.computed_at)
                    return data, age < RESULTS_TTL
                return None, False
        except Exception:
            return None, False

    def _persist_results(self, username: str, results: list[dict]):
        """Save formatted collection results to DB."""
        try:
            with get_db() as db:
                existing = db.get(CollectionResultsCache, username)
                if existing:
                    existing.data = results
                    existing.computed_at = time.time()
                else:
                    db.add(CollectionResultsCache(
                        username=username, data=results, computed_at=time.time()
                    ))
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist collection results for {username}: {e}")

    # ── Core logic ────────────────────────────────────────────────

    async def get_user_collections(self, username: str) -> list[UserCollection]:
        """Full collection scan — expensive, should be called from background tasks."""
        from app.services.factory import resolve_user_id
        uid = resolve_user_id(username)

        # 1. Get user's watched movies
        history = await self.tautulli.get_history(user_id=uid, limit=5000)
        user_movies = [e for e in history if e.media_type == "movie"]

        # 2. Resolve TMDB IDs for entries missing them
        needs_resolve = [(e.item_key, e.media_type) for e in user_movies if not e.tmdb_id]
        if needs_resolve:
            tmdb_map = await self.tautulli.resolve_tmdb_ids_batch(needs_resolve[:500])
            for e in user_movies:
                if not e.tmdb_id and e.item_key in tmdb_map:
                    e.tmdb_id = tmdb_map[e.item_key]

        user_watched_tmdb = {e.tmdb_id for e in user_movies if e.tmdb_id}
        logger.info(f"Collections: {username} watched {len(user_watched_tmdb)} unique movies")

        if not user_watched_tmdb:
            return []

        # 3. Check collection membership (L1 → L2 → TMDB API)
        unchecked = [tid for tid in user_watched_tmdb if tid not in self._movie_coll]
        if unchecked:
            sem = asyncio.Semaphore(15)
            new_mappings = []

            async def check_one(tid):
                async with sem:
                    result = await self.tmdb.get_movie_collection_id(tid)
                    cid = result["id"] if result else None
                    self._movie_coll[tid] = cid
                    new_mappings.append((tid, cid))

            await asyncio.gather(
                *[check_one(tid) for tid in unchecked], return_exceptions=True
            )
            self._persist_movie_coll_batch(new_mappings)
            logger.info(
                f"Checked {len(unchecked)} movies for collection membership "
                f"({len(new_mappings)} persisted)"
            )

        # 4. Find unique collections
        coll_ids = {
            self._movie_coll[tid]
            for tid in user_watched_tmdb
            if self._movie_coll.get(tid)
        }

        # 5. Fetch collection details (L1 → DB → TMDB API)
        new_colls = [cid for cid in coll_ids if cid not in self._coll_cache]
        if new_colls:
            sem = asyncio.Semaphore(10)

            async def fetch(cid):
                async with sem:
                    return await self.tmdb.get_collection(cid)

            results = await asyncio.gather(
                *[fetch(cid) for cid in new_colls], return_exceptions=True
            )
            for r in results:
                if isinstance(r, dict) and r.get("collection_id"):
                    self._coll_cache[r["collection_id"]] = r
                    self._persist_coll_detail(r["collection_id"], r)

        # 6. Get library TMDB IDs
        movies = await self.radarr.get_all_movies()
        library_tmdb = {m.tmdb_id for m in movies if m.tmdb_id}

        # 7. Build results
        results = []
        for coll_id in coll_ids:
            coll = self._coll_cache.get(coll_id)
            if not coll:
                continue

            parts = []
            watched_count = 0
            in_lib_count = 0
            missing = []

            for p in coll["parts"]:
                poster = (
                    f"https://image.tmdb.org/t/p/w342{p['poster_path']}"
                    if p.get("poster_path") else None
                )
                in_lib = p["tmdb_id"] in library_tmdb
                watched = p["tmdb_id"] in user_watched_tmdb

                part = CollectionPart(
                    tmdb_id=p["tmdb_id"],
                    title=p["title"],
                    year=p.get("year"),
                    poster_url=poster,
                    vote_average=p.get("vote_average", 0),
                    in_library=in_lib,
                    watched=watched,
                    release_date=p.get("release_date"),
                )
                parts.append(part)
                if watched:
                    watched_count += 1
                if in_lib:
                    in_lib_count += 1
                if not watched:
                    missing.append(part)

            total = len(parts)
            if total < 2 or watched_count == total:
                continue

            pct = round((watched_count / total) * 100, 1)
            poster = (
                f"https://image.tmdb.org/t/p/w342{coll['poster_path']}"
                if coll.get("poster_path") else None
            )
            backdrop = (
                f"https://image.tmdb.org/t/p/w1280{coll['backdrop_path']}"
                if coll.get("backdrop_path") else None
            )

            results.append(UserCollection(
                collection_id=coll_id,
                name=coll["name"],
                poster_url=poster,
                backdrop_url=backdrop,
                total_parts=total,
                watched_count=watched_count,
                in_library_count=in_lib_count,
                completion_pct=pct,
                parts=parts,
                missing_parts=missing,
            ))

        results.sort(key=lambda c: -c.completion_pct)
        logger.info(f"Collections result: {len(results)} incomplete collections for {username}")
        return results
