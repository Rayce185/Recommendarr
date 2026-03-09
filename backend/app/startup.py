"""Recommendarr startup lifecycle — service probing, warmup, scheduler.

Extracted from main.py for §7.7 compliance. Contains the lifespan
context manager, service probe logic, and background warmup tasks.
"""

import asyncio
import logging
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.services.factory import build_stack, init_user_map, get_stack
from app.services.rec_library import get_library_candidates
from app.services.cache import get_cache

logger = logging.getLogger("recommendarr")


async def _probe_services(stack) -> dict[str, bool]:
    """Probe all upstream services and return status map."""
    probes = {}
    for name, client in [
        ("tautulli", stack.tautulli),
        ("seerr", stack.seerr),
        ("radarr", stack.radarr),
        ("sonarr_tv", stack.sonarr_tv),
        ("sonarr_anime", stack.sonarr_anime),
    ]:
        try:
            probes[name] = await client.test_connection()
        except Exception:
            probes[name] = False
    return probes


async def _init_plex(stack, probes: dict):
    """Initialize Plex with retry logic and tvdb→tmdb bridge."""
    if not stack.plex:
        logger.info("Plex not configured — deep links disabled")
        return

    plex_ok = False
    for attempt in range(5):
        try:
            plex_ok = await stack.plex.test_connection()
            if plex_ok:
                if not stack.plex.machine_id:
                    await stack.plex.init()
                tvdb_to_tmdb: dict[int, int] = {}
                for sonarr_name, sonarr_client in [
                    ("sonarr_tv", stack.sonarr_tv),
                    ("sonarr_anime", stack.sonarr_anime),
                ]:
                    try:
                        all_series = await sonarr_client.get_all_series()
                        for s in all_series:
                            if s.tvdb_id and s.tmdb_id:
                                tvdb_to_tmdb[s.tvdb_id] = s.tmdb_id
                    except Exception as e:
                        logger.warning(f"Could not build tvdb bridge from {sonarr_name}: {e}")
                if tvdb_to_tmdb:
                    logger.info(f"Sonarr tvdb→tmdb bridge: {len(tvdb_to_tmdb)} mappings")
                await stack.plex.build_tmdb_map(tvdb_to_tmdb=tvdb_to_tmdb)
                logger.info(f"Plex TMDB map: {stack.plex.map_size} items across {len(stack.plex.sections)} sections")
                break
            else:
                logger.warning(f"Plex probe attempt {attempt+1}/5 failed — retrying in 3s")
                await asyncio.sleep(3)
        except Exception as e:
            logger.warning(f"Plex probe attempt {attempt+1}/5 error: {e} — retrying in 3s")
            await asyncio.sleep(3)

    probes["plex"] = plex_ok
    if not plex_ok:
        logger.error("Plex unreachable after 5 attempts — library filters and watched state unavailable")


async def _warm_profiles():
    """Background warmup: profiles, library, posters, collections, recs."""
    try:
        await asyncio.sleep(2)
        s = get_stack()
        cache = get_cache()
        if not s.profiler or not s.user_map:
            return

        active = list(s.user_map.values())[:3]
        warmed = 0

        # Warm taste profiles
        for username in active:
            if cache.get_profile(username, "all") is not None:
                continue
            try:
                _start = time.monotonic()
                profile = await s.profiler.build_profile(
                    username=username, domain="all",
                    depth_months=24, enrich_keywords=True, max_enrich=100,
                )
                cache.set_profile(username, "all", profile)
                warmed += 1
                logger.info(f"Profile warmed: {username} ({profile.total_watched} titles, {time.monotonic()-_start:.1f}s)")
            except Exception as e:
                logger.warning(f"Profile warming failed for {username}: {e}")

        # Warm library candidates
        try:
            _start = time.monotonic()
            await get_library_candidates(s.radarr, s.sonarr_tv, s.sonarr_anime, "all")
            logger.info(f"Library cache warmed ({time.monotonic()-_start:.1f}s)")
        except Exception as e:
            logger.debug(f"Library warming skipped: {e}")

        # Pre-warm data-layer caches (Radarr library IDs + per-user watched IDs)
        # Eliminates ~20s cold-start on collection-for-movie endpoint
        try:
            _start = time.monotonic()
            movies = await s.radarr.get_all_movies()
            library_ids = [m.tmdb_id for m in movies if m.tmdb_id]
            cache.set_generic("_radarr_library_ids", library_ids, ttl=300)
            from app.services.factory import resolve_user_id as _resolve_uid
            for username in active:
                uid = _resolve_uid(username)
                history = await s.tautulli.get_history(user_id=None, limit=10000)
                watched = [e.tmdb_id for e in history if e.user_id == uid and e.media_type == "movie" and e.tmdb_id]
                cache.set_generic(f"_watched_ids:{username}", watched, ttl=300)
            logger.info(f"Data-layer cache warmed: {len(library_ids)} library IDs, {len(active)} users ({time.monotonic()-_start:.1f}s)")
        except Exception as e:
            logger.debug(f"Data-layer warming skipped: {e}")

        # Enrich TVDB poster URLs with TMDB paths
        try:
            candidates = cache.get_library("all") or []
            tvdb_items = [
                c for c in candidates
                if (c.get("poster_path") or "").startswith("http")
                and "image.tmdb.org" not in (c.get("poster_path") or "")
            ]
            if tvdb_items and s.engine.tmdb:
                logger.info(f"Poster enrichment: {len(tvdb_items)} items need TMDB poster lookup")
                enriched = 0
                for item in tvdb_items:
                    try:
                        mt = item.get("media_type", "movie")
                        detail = await s.engine.tmdb.get_detail(item["tmdb_id"], mt)
                        if detail and detail.get("poster_path", "").startswith("/"):
                            item["poster_path"] = detail["poster_path"]
                            enriched += 1
                        if enriched % 30 == 0:
                            await asyncio.sleep(1)
                    except Exception:
                        pass
                if enriched:
                    cache.set_library("all", candidates)
                    logger.info(f"Poster enrichment done: {enriched}/{len(tvdb_items)} fixed")
        except Exception as e:
            logger.debug(f"Poster enrichment skipped: {e}")

        # Pre-warm collection scans
        try:
            from app.services.collections import CollectionService
            if s.tmdb and s.radarr and s.tautulli:
                if not hasattr(s, '_collection_svc') or s._collection_svc is None:
                    s._collection_svc = CollectionService(s.tmdb, s.radarr, s.tautulli)
                for username in active:
                    try:
                        sqlite_data, is_fresh = s._collection_svc.get_cached_results(username)
                        if is_fresh:
                            cache.set_collections(username, sqlite_data)
                            logger.info(f"Collections: {username} — served from SQLite L2 (fresh, skipping TMDB scan)")
                            continue
                        _start = time.monotonic()
                        colls = await s._collection_svc.get_user_collections(username)
                        coll_data = []
                        for c in colls:
                            coll_data.append({
                                "collection_id": c.collection_id, "name": c.name,
                                "poster_url": c.poster_url, "backdrop_url": c.backdrop_url,
                                "total_parts": c.total_parts, "watched_count": c.watched_count,
                                "in_library_count": c.in_library_count, "completion_pct": c.completion_pct,
                                "parts": [{"tmdb_id": p.tmdb_id, "title": p.title, "year": p.year,
                                           "poster_url": p.poster_url, "vote_average": p.vote_average,
                                           "in_library": p.in_library, "watched": p.watched,
                                           "release_date": p.release_date} for p in c.parts],
                                "missing": [{"tmdb_id": p.tmdb_id, "title": p.title, "year": p.year,
                                             "poster_url": p.poster_url, "vote_average": p.vote_average,
                                             "in_library": p.in_library, "watched": p.watched,
                                             "release_date": p.release_date} for p in c.missing_parts],
                            })
                        cache.set_collections(username, coll_data)
                        s._collection_svc._persist_results(username, coll_data)
                        logger.info(f"Collections warmed: {username} ({len(colls)} collections, {time.monotonic()-_start:.1f}s)")
                    except Exception as e:
                        logger.warning(f"Collection warming failed for {username}: {e}")
        except Exception as e:
            logger.debug(f"Collection warming skipped: {e}")

        # Pre-warm recommendations
        if warmed > 0:
            from app.services.recommender import RecommendationRequest
            from dataclasses import asdict
            for username in active:
                if not cache.get_profile(username, "all"):
                    continue
                for mode in ["tonight", "grab"]:
                    try:
                        _start = time.monotonic()
                        req = RecommendationRequest(username=username, mode=mode, domain="all", limit=30)
                        results = await s.engine.recommend(req)
                        if results:
                            recs_data = []
                            for r in results:
                                try:
                                    recs_data.append(asdict(r))
                                except Exception:
                                    recs_data.append(r.__dict__ if hasattr(r, "__dict__") else {})
                            cache.set_recs(username, mode, "all", {
                                "recommendations": recs_data,
                                "meta": {"username": username, "mode": mode, "count": len(results)},
                            })
                            logger.info(f"Recs warmed: {username}/{mode} ({len(results)} items, {time.monotonic()-_start:.1f}s)")
                    except Exception as e:
                        logger.warning(f"Rec warming failed for {username}/{mode}: {e}")

        if warmed:
            logger.info(f"Startup warming done: {warmed} profiles + library + recs cached")
    except Exception as e:
        logger.warning(f"Profile warming error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, migrate data, build service stack, probe integrations."""
    logger.info("=== Recommendarr starting ===")

    from app.database import init_db
    init_db()

    from app.services.db_migrate import migrate_json_to_sqlite
    migrate_json_to_sqlite()

    # ChromaDB sync (optional)
    from app.services.chroma_sync import init_chroma_sync
    from app.services.settings_store import get_settings_store
    store = get_settings_store()
    chromadb_url = store.get("chromadb_url") or settings.chromadb_url
    embed_url = store.get("llm_base_url") or settings.llm_base_url
    embed_model = store.get("embedding_model") or settings.embedding_model
    if chromadb_url and embed_url:
        sync = init_chroma_sync(chromadb_url, embed_url, embed_model)
        if sync:
            logger.info(f"ChromaDB sync enabled → {chromadb_url}")
    else:
        logger.info("ChromaDB sync disabled (no chromadb_url configured)")

    stack = build_stack()

    # Probe services
    probes = await _probe_services(stack)
    await _init_plex(stack, probes)

    ok_count = sum(1 for v in probes.values() if v)
    logger.info(f"Service probes: {ok_count}/{len(probes)} OK — {probes}")
    if not probes.get("tautulli"):
        logger.error("CRITICAL: Tautulli not reachable — watch history unavailable")
    if not probes.get("seerr"):
        logger.warning("Seerr not reachable — using TMDB direct for metadata")

    await init_user_map(stack)
    logger.info("=== Recommendarr ready ===")

    asyncio.create_task(_warm_profiles())
    from app.services.tmdb_enrichment import run_tmdb_enrichment
    asyncio.create_task(run_tmdb_enrichment())

    from app.services.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Scheduled refresh background task started")

    yield

    # Cleanup
    from app.services.chroma_sync import get_chroma_sync
    sync = get_chroma_sync()
    if sync:
        await sync.close()
    sched = get_scheduler()
    await sched.stop()
    logger.info("=== Recommendarr shutting down ===")
