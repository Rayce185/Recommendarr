"""Background refresh task — cache warming + SSE progress reporting.

Split from api/refresh.py for §7.7 compliance. Contains the job storage,
RefreshStep model, and the background task that runs the actual refresh.
"""

import asyncio
import json
import logging
import time
from app.services.rec_library import get_library_candidates
from typing import Optional

logger = logging.getLogger(__name__)


# ── Job storage (in-memory, single-instance) ─────────────────────

_jobs: dict[str, dict] = {}   # job_id -> {queue, status, started_at, ...}
_active_job: Optional[str] = None  # Only one refresh at a time


def get_jobs() -> dict[str, dict]:
    return _jobs


def get_active_job() -> Optional[str]:
    return _active_job


def set_active_job(job_id: Optional[str]):
    global _active_job
    _active_job = job_id


class RefreshStep:
    """Progress event pushed to SSE stream."""
    def __init__(self, step: int, total: int, label: str, elapsed_ms: int, done: bool = False, error: str = None):
        self.step = step
        self.total = total
        self.label = label
        self.elapsed_ms = elapsed_ms
        self.done = done
        self.error = error

    def to_sse(self) -> str:
        data = {
            "step": self.step,
            "total": self.total,
            "label": self.label,
            "elapsed_ms": self.elapsed_ms,
            "done": self.done,
        }
        if self.error:
            data["error"] = self.error
        return f"data: {json.dumps(data)}\n\n"


async def run_refresh(job_id: str, username: str):
    """Execute cache refresh: profile first, then modes in parallel, cache results."""
    job = _jobs[job_id]
    queue: asyncio.Queue = job["queue"]
    start = time.time()

    from app.services.cache import get_cache
    from app.services.factory import get_stack
    from app.services.recommender import RecommendationRequest
    from app.api.rec_helpers import rec_to_dict
    from app.services.feedback import get_feedback_store

    cache = get_cache()
    stack = get_stack()

    steps = [
        ("Clearing stale caches", "clear"),
        ("Loading libraries", "libraries"),
        ("Building taste profile", "profile"),
        ("Generating recommendations", "recs_parallel"),
        ("Fetching Trending", "trending"),
        ("Pre-warming collections", "collections"),
    ]
    total = len(steps)

    async def _send(step_num, label):
        elapsed = int((time.time() - start) * 1000)
        await queue.put(RefreshStep(step_num, total, label, elapsed))

    def _cache_recs(mode, recs):
        """Format + cache recommendation results."""
        fb_store = get_feedback_store()
        response = {
            "recommendations": [rec_to_dict(r, plex=stack.plex) for r in recs],
            "meta": {"username": username, "mode": mode, "domain": "all",
                     "count": len(recs), "cached": False},
        }
        for rec in response["recommendations"]:
            rec["user_feedback"] = fb_store.get_action(username, rec["tmdb_id"])
        cache.set_recs(username, mode, "all", response)
        return len(recs)

    try:
        # Step 1: Clear caches
        step_start = time.time()
        await _send(1, "Clearing stale caches")
        cache.invalidate_all()
        cache.set_step_duration("clear", int((time.time() - step_start) * 1000))

        # Step 2: Pre-warm library candidates
        step_start = time.time()
        await _send(2, "Loading libraries")
        await get_library_candidates(stack.radarr, stack.sonarr_tv, stack.sonarr_anime, "all")
        cache.set_step_duration("libraries", int((time.time() - step_start) * 1000))
        logger.info(f"Refresh: libraries loaded in {time.time() - step_start:.1f}s")

        # Step 3: Build taste profile
        step_start = time.time()
        await _send(3, "Building taste profile")
        profile = await stack.profiler.build_profile(
            username=username, domain="all", enrich_keywords=True, max_enrich=100)
        cache.set_profile(username, "all", profile)
        cache.set_step_duration("profile", int((time.time() - step_start) * 1000))

        # Step 4: Run tonight + grab + rediscover in parallel
        step_start = time.time()
        await _send(4, "Generating recommendations (parallel)")

        async def _run_mode(mode):
            t0 = time.time()
            try:
                req = RecommendationRequest(
                    username=username, mode=mode, domain="all",
                    limit=30, skip_explanations=True)
                recs = await stack.engine.recommend(req)
                count = _cache_recs(mode, recs)
                ms = int((time.time() - t0) * 1000)
                cache.set_step_duration(mode, ms)
                logger.info(f"Refresh: {mode} done — {count} recs in {ms}ms")
                return mode, count, ms
            except Exception as e:
                logger.warning(f"Refresh: {mode} failed: {e}")
                cache.set_step_duration(mode, int((time.time() - t0) * 1000))
                return mode, 0, int((time.time() - t0) * 1000)

        results = await asyncio.gather(
            _run_mode("tonight"),
            _run_mode("grab"),
            _run_mode("rediscover"),
            return_exceptions=True,
        )
        cache.set_step_duration("recs_parallel", int((time.time() - step_start) * 1000))

        # Step 5: Trending
        step_start = time.time()
        await _send(5, "Fetching Trending")
        try:
            if stack.tmdb:
                await stack.tmdb.get_trending("all", "week", 1)
            else:
                await stack.seerr.get_trending(page=1)
        except Exception as e:
            logger.warning(f"Refresh: trending failed: {e}")
        cache.set_step_duration("trending", int((time.time() - step_start) * 1000))

        # Step 6: Pre-warm collections
        step_start = time.time()
        await _send(6, "Pre-warming collections")
        try:
            from app.services.collections import CollectionService
            if not hasattr(stack, "_collection_svc") or stack._collection_svc is None:
                stack._collection_svc = CollectionService(stack.tmdb, stack.radarr, stack.tautulli)
            collections = await stack._collection_svc.get_user_collections(username)
            coll_list = [
                {
                    "collection_id": c.collection_id,
                    "name": c.name,
                    "poster_url": c.poster_url,
                    "backdrop_url": c.backdrop_url,
                    "total_parts": c.total_parts,
                    "watched_count": c.watched_count,
                    "in_library_count": c.in_library_count,
                    "completion_pct": c.completion_pct,
                    "parts": [{"tmdb_id": p.tmdb_id, "title": p.title, "year": p.year,
                               "poster_url": p.poster_url, "vote_average": p.vote_average,
                               "in_library": p.in_library, "watched": p.watched,
                               "release_date": p.release_date} for p in c.parts],
                    "missing": [{"tmdb_id": p.tmdb_id, "title": p.title, "year": p.year,
                                 "poster_url": p.poster_url, "vote_average": p.vote_average,
                                 "in_library": p.in_library, "watched": p.watched,
                                 "release_date": p.release_date} for p in c.missing_parts],
                }
                for c in collections
            ]
            cache.set_collections(username, coll_list)
            stack._collection_svc._persist_results(username, coll_list)
            logger.info(f"Refresh: collections pre-warmed — {len(coll_list)} collections")
        except Exception as e:
            logger.warning(f"Refresh: collections pre-warm failed: {e}")
        cache.set_step_duration("collections", int((time.time() - step_start) * 1000))

        total_ms = int((time.time() - start) * 1000)
        cache.set_last_refresh(total_ms)
        await queue.put(RefreshStep(total, total, "Complete", total_ms, done=True))
        logger.info(f"Refresh complete in {total_ms}ms for user={username}")

    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        await queue.put(RefreshStep(0, total, f"Error: {e}", elapsed, done=True, error=str(e)))
        logger.error(f"Refresh failed: {e}")
    finally:
        job["status"] = "complete"
        set_active_job(None)
