"""Collection completion service — finds partially watched franchises."""

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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

    DB_PATH = "/app/data/recommendarr.db"

    def __init__(self, tmdb, radarr, tautulli):
        self.tmdb = tmdb
        self.radarr = radarr
        self.tautulli = tautulli
        # Cache: tmdb_movie_id → collection_id (or None)
        self._movie_coll: dict[int, int | None] = {}
        # Cache: collection_id → full data
        self._coll_cache: dict[int, dict] = {}
        # Load persisted collection membership from SQLite
        self._init_persistent_cache()

    def _init_persistent_cache(self):
        """Load movie→collection mapping from SQLite to survive container restarts."""
        import sqlite3
        try:
            conn = sqlite3.connect(self.DB_PATH)
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS movie_collection_map (
                tmdb_id INTEGER PRIMARY KEY,
                collection_id INTEGER
            )""")
            conn.commit()
            c.execute("SELECT tmdb_id, collection_id FROM movie_collection_map")
            for tid, cid in c.fetchall():
                self._movie_coll[tid] = cid
            conn.close()
            if self._movie_coll:
                logger.info(f"Loaded {len(self._movie_coll)} movie→collection mappings from SQLite")
        except Exception as e:
            logger.warning(f"Could not load collection cache from SQLite: {e}")

    def _persist_movie_coll(self, tmdb_id: int, collection_id: int | None):
        """Save a single movie→collection mapping to SQLite."""
        import sqlite3
        try:
            conn = sqlite3.connect(self.DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO movie_collection_map (tmdb_id, collection_id) VALUES (?, ?)",
                      (tmdb_id, collection_id))
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-critical — in-memory cache still works

    async def get_user_collections(self, username: str) -> list[UserCollection]:
        """Get collections with completion status for a specific user."""
        from app.services.factory import resolve_user_id
        uid = resolve_user_id(username)

        # 1. Get user's watched movies
        history = await self.tautulli.get_history(user_id=None, limit=10000)
        user_movies = [e for e in history if e.user_id == uid and e.media_type == "movie"]

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

        # 3. Check which watched movies belong to collections
        #    (cached — only query TMDB for new ones)
        unchecked = [tid for tid in user_watched_tmdb if tid not in self._movie_coll]
        if unchecked:
            sem = asyncio.Semaphore(8)

            async def check_one(tid):
                async with sem:
                    result = await self.tmdb.get_movie_collection_id(tid)
                    cid = result["id"] if result else None
                    self._movie_coll[tid] = cid
                    self._persist_movie_coll(tid, cid)

            await asyncio.gather(*[check_one(tid) for tid in unchecked],
                                  return_exceptions=True)
            logger.info(f"Checked {len(unchecked)} movies for collection membership")

        # 4. Find unique collections the user has partial progress in
        coll_ids = set()
        for tid in user_watched_tmdb:
            cid = self._movie_coll.get(tid)
            if cid:
                coll_ids.add(cid)

        # 5. Fetch collection details (cached)
        new_colls = [cid for cid in coll_ids if cid not in self._coll_cache]
        if new_colls:
            sem = asyncio.Semaphore(5)

            async def fetch(cid):
                async with sem:
                    return await self.tmdb.get_collection(cid)

            results = await asyncio.gather(*[fetch(cid) for cid in new_colls],
                                            return_exceptions=True)
            for r in results:
                if isinstance(r, dict) and r.get("collection_id"):
                    self._coll_cache[r["collection_id"]] = r

        # 6. Get library TMDB IDs for in_library check
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
                poster = f"https://image.tmdb.org/t/p/w342{p['poster_path']}" if p.get("poster_path") else None
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
                continue  # Skip single-movie or complete collections

            pct = round((watched_count / total) * 100, 1)
            poster = f"https://image.tmdb.org/t/p/w342{coll['poster_path']}" if coll.get("poster_path") else None
            backdrop = f"https://image.tmdb.org/t/p/w1280{coll['backdrop_path']}" if coll.get("backdrop_path") else None

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
