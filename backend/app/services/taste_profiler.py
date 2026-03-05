"""Taste Profiler v2 — API-first, Tautulli as source of truth.

Computes user taste profiles entirely from Tautulli watch history API.
Profiles are cached in PostgreSQL for performance but are always rebuildable
from Tautulli — the DB is a cache, not a source of truth.

Architecture:
  1. Pull full watch history from Tautulli API (paginated)
  2. Enrich with Seerr metadata (genres, keywords, cast/crew)
  3. Score each watch event (completion, recency, frequency)
  4. Aggregate into genre/keyword/personnel vectors per domain
  5. Cache in DB, refresh on schedule or demand

No embeddings. No local model. Pure arithmetic on structured metadata.
"""

import math
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

from app.clients.tautulli import TautulliClient
from app.clients.seerr import SeerrClient
from app.clients.servarr import RadarrClient, SonarrClient

logger = logging.getLogger(__name__)


# ── Signal weights (from spec §3.1) ─────────────────────────────

SIGNAL_WEIGHTS = {
    "completion_full": 5.0,       # ≥85% watched
    "completion_good": 2.0,       # 40-84% watched
    "completion_abandoned": -3.0, # <20% watched
    "rewatch": 4.0,               # Each additional watch
    "recency_halflife_days": 180, # Exponential decay half-life
}


# ── Data structures ──────────────────────────────────────────────

@dataclass
class GenreAffinity:
    """Weighted genre preference for a user."""
    genre: str
    score: float = 0.0        # Normalized 0.0-1.0
    raw_score: float = 0.0    # Pre-normalization
    watch_count: int = 0      # How many titles with this genre
    avg_completion: float = 0.0
    total_hours: float = 0.0


@dataclass
class KeywordAffinity:
    """Weighted TMDB keyword preference."""
    keyword: str
    score: float = 0.0
    occurrence_count: int = 0


@dataclass
class PersonnelAffinity:
    """Director/actor preference from watch patterns."""
    name: str
    role: str                  # "director" | "actor"
    score: float = 0.0
    title_count: int = 0
    avg_completion: float = 0.0


@dataclass
class TasteProfile:
    """Complete taste profile for a user across one or all domains."""
    user_id: str
    username: str
    domain: str                # "movies" | "tv" | "anime" | "all"
    built_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_watched: int = 0
    total_hours: float = 0.0
    avg_completion: float = 0.0
    rewatch_count: int = 0
    # Vectors
    genres: list[GenreAffinity] = field(default_factory=list)
    keywords: list[KeywordAffinity] = field(default_factory=list)
    personnel: list[PersonnelAffinity] = field(default_factory=list)
    # Negative signals
    avoided_genres: list[GenreAffinity] = field(default_factory=list)
    avoided_keywords: list[KeywordAffinity] = field(default_factory=list)

    def top_genres(self, n: int = 8) -> list[GenreAffinity]:
        return sorted(self.genres, key=lambda g: g.score, reverse=True)[:n]

    def top_keywords(self, n: int = 15) -> list[KeywordAffinity]:
        return sorted(self.keywords, key=lambda k: k.score, reverse=True)[:n]

    def top_personnel(self, n: int = 10) -> list[PersonnelAffinity]:
        return sorted(self.personnel, key=lambda p: p.score, reverse=True)[:n]

    def genre_score(self, genre: str) -> float:
        """Look up score for a specific genre."""
        for g in self.genres:
            if g.genre == genre:
                return g.score
        return 0.0

    def keyword_score(self, keyword: str) -> float:
        """Look up score for a specific keyword."""
        for k in self.keywords:
            if k.keyword == keyword:
                return k.score
        return 0.0


# ── Plex library → domain mapping ────────────────────────────────
# Maps Tautulli library section IDs to recommendation domains.
# These come from the verified Plex libraries on Ray's server.

DEFAULT_LIBRARY_DOMAINS = {
    # Movies
    "14": "movies",    # Movies
    "20": "movies",    # Kinderfilme
    # TV
    "2": "tv",         # TV Series
    "7": "tv",         # Kinderserien
    # Anime
    "10": "anime",     # Anime
    "15": "anime",     # Anime-Ecchi
    "17": "anime",     # Anime-Hentai
}


class TasteProfiler:
    """Builds taste profiles from Tautulli API + Seerr metadata.

    API-first architecture — Tautulli is the source of truth for watch
    history, Seerr provides TMDB metadata enrichment. PostgreSQL stores
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
            enrich_keywords: Whether to fetch TMDB keywords via Seerr (slower but richer)
            max_enrich: Max titles to enrich with keywords (rate limit control)
        """
        logger.info(f"Building taste profile for {username} (domain={domain}, depth={depth_months}mo)")

        # 1. Resolve username → numeric user_id (BEFORE fetching history)
        user_id_match = username
        try:
            users = await self.tautulli.get_users()
            for u in users:
                uname = u.get("username", "") or u.get("friendly_name", "")
                if uname == username:
                    user_id_match = str(u.get("user_id", ""))
                    logger.info(f"Resolved username '{username}' → user_id '{user_id_match}'")
                    break
        except Exception as e:
            logger.warning(f"Could not resolve username: {e}")

        # 2. Pull watch history from Tautulli (filtered by user_id = fewer events)
        since = datetime.now(timezone.utc) - timedelta(days=depth_months * 30)
        history = await self.tautulli.get_history(user_id=user_id_match, since=since, limit=10000)

        # Filter to this user (safety check — API filter should handle it)
        user_events = [
            e for e in history
            if str(e.user_id) == user_id_match
            or str(e.user_id) == username
            or e.user_id == username
        ]
        if not user_events:
            logger.warning(f"No events found for user_id={user_id_match} (username={username})")

        logger.info(f"Found {len(user_events)} watch events for {username}")
        import time as _time
        _t0 = _time.monotonic()

        # 2. Group by item (rating_key) to compute per-title stats
        by_item: dict[str, list] = defaultdict(list)
        for event in user_events:
            by_item[event.item_key].append(event)

        # 3. Resolve TMDB IDs for items that need it
        import time as _timer
        _step3_start = _timer.monotonic()
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

        _t1 = _time.monotonic()
        logger.info(f"TMDB ID resolution: {_t1-_t0:.1f}s ({len(items_needing_tmdb)} items needed resolution)")

        _step3_end = _timer.monotonic()
        logger.info(f"TMDB ID resolution: {_step3_end - _step3_start:.1f}s ({len(items_needing_tmdb)} items)")

        # 4. Score each title and collect metadata
        now = datetime.now(timezone.utc)
        genre_scores: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "count": 0, "completions": [], "hours": 0.0})
        keyword_scores: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "count": 0})
        personnel_scores: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "count": 0, "completions": [], "role": ""})
        total_watched = 0
        total_hours = 0.0
        completions = []
        rewatch_count = 0
        enriched = 0
        items_to_enrich = []  # (item_key, tmdb_id, media_type)

        # Pre-enrich: SQLite cache first, TMDB API for misses only
        _enrich_cache = {}
        if enrich_keywords:
            import asyncio
            import json as _json
            from app.database import get_db
            from app.models.tables import TmdbCache
            from sqlalchemy import select, and_

            # Sort by watch count (most-watched first)
            _candidates = []
            for _ik, _evts in by_item.items():
                _p = _evts[0]
                _tid = _p.tmdb_id
                if _tid:
                    _mt = "movie" if _p.media_type == "movie" else "tv"
                    _candidates.append((_ik, _tid, _mt, len(_evts)))
            _candidates.sort(key=lambda x: x[3], reverse=True)
            _enrich_items = [(_ik, _tid, _mt) for _ik, _tid, _mt, _ in _candidates[:max_enrich]]

            # Phase 1: Check SQLite cache
            _cache_hits = 0
            _cache_misses = []  # (item_key, tmdb_id, media_type)
            try:
                with get_db() as db:
                    for _ik, _tid, _mt in _enrich_items:
                        row = db.execute(
                            select(TmdbCache).where(
                                and_(TmdbCache.tmdb_id == _tid, TmdbCache.media_type == _mt)
                            )
                        ).scalar_one_or_none()
                        if row and row.genres:
                            genres = row.genres if isinstance(row.genres, list) else _json.loads(row.genres) if row.genres else []
                            keywords = row.keywords if isinstance(row.keywords, list) else _json.loads(row.keywords) if row.keywords else []
                            cast_crew = row.cast_crew if isinstance(row.cast_crew, dict) else _json.loads(row.cast_crew) if row.cast_crew else {}
                            _enrich_cache[_ik] = {
                                "genres": genres,
                                "keywords": keywords,
                                "cast": cast_crew.get("cast", [])[:5],
                                "directors": cast_crew.get("directors", []),
                                "original_language": row.original_language,
                            }
                            _cache_hits += 1
                        else:
                            _cache_misses.append((_ik, _tid, _mt))
            except Exception as e:
                logger.debug(f"SQLite cache read failed: {e}")
                _cache_misses = _enrich_items

            # Phase 2: Fetch misses from TMDB API (parallel)
            _api_fetched = 0
            if _cache_misses:
                async def _fetch_and_store(ik, tid, mt):
                    try:
                        if self.tmdb:
                            d = await self.tmdb.get_detail(tid, mt)
                            result = {
                                "genres": d.get("genres", []),
                                "keywords": d.get("keywords", []),
                                "cast": [c["name"] for c in d.get("cast", [])[:5]],
                                "directors": [c["name"] for c in d.get("crew", []) if c.get("job") == "Director"],
                                "original_language": d.get("original_language"),
                            }
                            # Persist to SQLite
                            try:
                                with get_db() as db:
                                    existing = db.execute(
                                        select(TmdbCache).where(
                                            and_(TmdbCache.tmdb_id == tid, TmdbCache.media_type == mt)
                                        )
                                    ).scalar_one_or_none()
                                    if existing:
                                        existing.genres = _json.dumps(d.get("genres", []))
                                        existing.keywords = _json.dumps(d.get("keywords", []))
                                        existing.cast_crew = _json.dumps({"cast": result["cast"], "directors": result["directors"]})
                                        existing.title = d.get("title", "")
                                        existing.year = d.get("year")
                                        existing.overview = d.get("overview", "")
                                        existing.vote_average = d.get("vote_average", 0)
                                    else:
                                        db.add(TmdbCache(
                                            tmdb_id=tid, media_type=mt,
                                            title=d.get("title", ""),
                                            year=d.get("year"),
                                            genres=_json.dumps(d.get("genres", [])),
                                            keywords=_json.dumps(d.get("keywords", [])),
                                            cast_crew=_json.dumps({"cast": result["cast"], "directors": result["directors"]}),
                                            overview=d.get("overview", ""),
                                            vote_average=d.get("vote_average", 0),
                                            poster_path=d.get("poster_path"),
                                            backdrop_path=d.get("backdrop_path"),
                                            original_language=d.get("original_language"),
                                        ))
                                    db.commit()
                            except Exception:
                                pass  # Cache write failure is non-fatal
                            return ik, result
                        else:
                            d = await self.seerr.get_detail(tid, mt)
                            return ik, {"genres": d.genres, "keywords": d.keywords, "cast": [c["name"] for c in d.cast[:5]], "directors": d.directors}
                    except Exception:
                        return ik, {}

                _sem = asyncio.Semaphore(20)
                async def _limited(ik, tid, mt):
                    async with _sem:
                        return await _fetch_and_store(ik, tid, mt)

                _tasks = [_limited(ik, tid, mt) for ik, tid, mt in _cache_misses]
                _results = await asyncio.gather(*_tasks, return_exceptions=True)
                for r in _results:
                    if isinstance(r, tuple):
                        _enrich_cache[r[0]] = r[1]
                        _api_fetched += 1

            enriched = len(_enrich_cache)
            logger.info(f"Enriched {enriched} titles ({_cache_hits} cached, {_api_fetched} from TMDB API)")

        for item_key, events in by_item.items():
            primary = events[0]

            # Domain filtering
            # For now, use media_type as proxy — episode=tv/anime, movie=movies
            # Full domain resolution needs library_section_id from Tautulli metadata
            item_domain = "movies" if primary.media_type == "movie" else "tv"
            if domain != "all" and item_domain != domain:
                continue

            # Compute per-title signals
            watch_count = len(events)
            best_completion = max(e.completion_pct for e in events)
            total_duration = sum(e.duration_seconds for e in events)
            most_recent = max((e.started_at for e in events if e.started_at), default=now)
            # Ensure timezone-aware for comparison
            if most_recent.tzinfo is None:
                most_recent = most_recent.replace(tzinfo=timezone.utc)

            # Completion signal
            if best_completion >= 85:
                completion_signal = SIGNAL_WEIGHTS["completion_full"]
            elif best_completion >= 40:
                completion_signal = SIGNAL_WEIGHTS["completion_good"]
            elif best_completion < 20 and watch_count == 1:
                completion_signal = SIGNAL_WEIGHTS["completion_abandoned"]
            else:
                completion_signal = 0.0

            # Rewatch signal
            rewatch_signal = 0.0
            if watch_count > 1:
                rewatch_signal = SIGNAL_WEIGHTS["rewatch"] * min(watch_count - 1, 5)
                rewatch_count += watch_count - 1

            # Recency decay
            days_ago = (now - most_recent).days if most_recent.tzinfo else (now.replace(tzinfo=None) - most_recent).days
            decay = math.exp(-0.693 * days_ago / SIGNAL_WEIGHTS["recency_halflife_days"])

            # Total item score
            item_score = (completion_signal + rewatch_signal) * decay

            total_watched += 1
            total_hours += total_duration / 3600
            completions.append(best_completion)

            # 5. Get metadata from Seerr (if we have TMDB ID)
            tmdb_id = primary.tmdb_id
            genres = []
            keywords = []
            cast_names = []
            director_names = []

            if tmdb_id and item_key in _enrich_cache:
                meta = _enrich_cache[item_key]
                genres = meta.get("genres", [])
                keywords = meta.get("keywords", [])
                cast_names = meta.get("cast", [])
                director_names = meta.get("directors", [])

            # 6. Accumulate into vectors
            # Split "Animation" into "Anime" (Japanese) vs "Animation" (Western)
            orig_lang = None
            if tmdb_id and item_key in _enrich_cache:
                orig_lang = _enrich_cache[item_key].get("original_language")
            processed_genres = []
            for genre in genres:
                if genre == "Animation" and orig_lang == "ja":
                    processed_genres.append("Anime")
                else:
                    processed_genres.append(genre)
            for genre in processed_genres:
                g = genre_scores[genre]
                g["score"] += item_score
                g["count"] += 1
                g["completions"].append(best_completion)
                g["hours"] += total_duration / 3600

            for kw in keywords:
                k = keyword_scores[kw]
                k["score"] += item_score
                k["count"] += 1

            for name in director_names:
                p = personnel_scores[f"director:{name}"]
                p["score"] += item_score * 1.5  # Directors weighted higher
                p["count"] += 1
                p["completions"].append(best_completion)
                p["role"] = "director"

            for name in cast_names:
                p = personnel_scores[f"actor:{name}"]
                p["score"] += item_score
                p["count"] += 1
                p["completions"].append(best_completion)
                p["role"] = "actor"

        # 7. Normalize scores to 0.0–1.0
        max_genre_score = max((g["score"] for g in genre_scores.values()), default=1.0)
        max_kw_score = max((k["score"] for k in keyword_scores.values()), default=1.0)
        max_personnel_score = max((p["score"] for p in personnel_scores.values()), default=1.0)

        if max_genre_score == 0:
            max_genre_score = 1.0
        if max_kw_score == 0:
            max_kw_score = 1.0
        if max_personnel_score == 0:
            max_personnel_score = 1.0

        genres_list = []
        avoided_genres = []
        for genre, data in genre_scores.items():
            normalized = data["score"] / max_genre_score
            avg_comp = sum(data["completions"]) / len(data["completions"]) if data["completions"] else 0
            ga = GenreAffinity(
                genre=genre,
                score=round(max(0.0, min(1.0, normalized)), 3),
                raw_score=round(data["score"], 2),
                watch_count=data["count"],
                avg_completion=round(avg_comp, 1),
                total_hours=round(data["hours"], 1),
            )
            if data["score"] < 0:
                avoided_genres.append(ga)
            else:
                genres_list.append(ga)

        keywords_list = []
        avoided_keywords = []
        for kw, data in keyword_scores.items():
            normalized = data["score"] / max_kw_score
            ka = KeywordAffinity(
                keyword=kw,
                score=round(max(0.0, min(1.0, normalized)), 3),
                occurrence_count=data["count"],
            )
            if data["score"] < 0:
                avoided_keywords.append(ka)
            else:
                keywords_list.append(ka)

        personnel_list = []
        for key, data in personnel_scores.items():
            role, name = key.split(":", 1)
            normalized = data["score"] / max_personnel_score
            avg_comp = sum(data["completions"]) / len(data["completions"]) if data["completions"] else 0
            personnel_list.append(PersonnelAffinity(
                name=name,
                role=role,
                score=round(max(0.0, min(1.0, normalized)), 3),
                title_count=data["count"],
                avg_completion=round(avg_comp, 1),
            ))

        avg_completion = sum(completions) / len(completions) if completions else 0.0

        profile = TasteProfile(
            user_id=username,
            username=username,
            domain=domain,
            total_watched=total_watched,
            total_hours=round(total_hours, 1),
            avg_completion=round(avg_completion, 1),
            rewatch_count=rewatch_count,
            genres=genres_list,
            keywords=keywords_list,
            personnel=personnel_list,
            avoided_genres=avoided_genres,
            avoided_keywords=avoided_keywords,
        )

        logger.info(
            f"Profile built for {username}: {total_watched} titles, "
            f"{len(genres_list)} genres, {len(keywords_list)} keywords, "
            f"{len(personnel_list)} personnel, {enriched} enriched via TMDB"
        )

        return profile

    async def get_collaborative_peers(
        self,
        username: str,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """Find users with similar taste based on watch overlap.

        Returns list of (username, similarity_score) pairs.
        Used for collaborative filtering: "users who watched X also watched Y."
        """
        # Get this user's history
        user_history = await self.tautulli.get_history(user_id=None, limit=10000)
        user_items = {e.item_key for e in user_history if e.user_id == username}

        if not user_items:
            return []

        # Group all history by user
        by_user: dict[str, set] = defaultdict(set)
        for event in user_history:
            if event.user_id != username:
                by_user[event.user_id].add(event.item_key)

        # Jaccard similarity
        peers = []
        for other_user, other_items in by_user.items():
            intersection = len(user_items & other_items)
            union = len(user_items | other_items)
            if union > 0 and intersection >= 3:  # Minimum 3 shared items
                similarity = intersection / union
                peers.append((other_user, round(similarity, 3)))

        peers.sort(key=lambda x: x[1], reverse=True)
        return peers[:limit]

    async def get_collaborative_suggestions(
        self,
        username: str,
        known_item_keys: set[str],
        limit: int = 20,
    ) -> list[tuple[str, float, str]]:
        """Get items watched by similar users but not by this user.

        Returns list of (item_key, peer_score, peer_username) tuples.
        """
        peers = await self.get_collaborative_peers(username, limit=10)
        if not peers:
            return []

        suggestions: dict[str, tuple[float, str]] = {}
        user_history = await self.tautulli.get_history(user_id=None, limit=10000)

        for peer_name, similarity in peers:
            peer_events = [e for e in user_history if e.user_id == peer_name]
            for event in peer_events:
                if event.item_key not in known_item_keys and event.completion_pct >= 70:
                    key = event.item_key
                    existing_score = suggestions.get(key, (0.0, ""))[0]
                    new_score = existing_score + similarity * (event.completion_pct / 100)
                    if new_score > existing_score:
                        suggestions[key] = (new_score, peer_name)

        results = [(key, score, peer) for key, (score, peer) in suggestions.items()]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
