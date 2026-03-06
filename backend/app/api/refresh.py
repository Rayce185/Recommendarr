"""Cache refresh API with SSE progress streaming.

POST /cache/refresh        — Start a background refresh job
GET  /cache/refresh/status — Current refresh state + last duration
GET  /cache/refresh/{job_id}/stream — SSE event stream for live progress
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.factory import get_stack
from app.services.cache import get_cache
from app.services.profile_overrides import get_override_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])

# ── Job storage (in-memory, single-instance) ─────────────────────

_jobs: dict[str, dict] = {}   # job_id -> {queue, status, started_at, ...}
_active_job: Optional[str] = None  # Only one refresh at a time


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
        import json
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


# ── Background refresh task ──────────────────────────────────────

async def _run_refresh(job_id: str, username: str):
    """Execute cache refresh: profile first, then modes in parallel, cache results."""
    global _active_job
    job = _jobs[job_id]
    queue: asyncio.Queue = job["queue"]
    start = time.time()
    cache = get_cache()
    stack = get_stack()

    # Import here to avoid circular
    from app.services.recommender import RecommendationRequest
    from app.api.recommendations import _rec_to_dict, _img_url
    from app.services.feedback import get_feedback_store

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
        """Format + cache recommendation results (same format as API endpoint)."""
        fb_store = get_feedback_store()
        response = {
            "recommendations": [_rec_to_dict(r, plex=stack.plex) for r in recs],
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

        # Step 2: Pre-warm library candidates (one fetch, cached for all modes)
        step_start = time.time()
        await _send(2, "Loading libraries")
        await stack.engine._get_library_candidates("all")
        cache.set_step_duration("libraries", int((time.time() - step_start) * 1000))
        logger.info(f"Refresh: libraries loaded in {time.time() - step_start:.1f}s")

        # Step 3: Build taste profile (needed by scoring)
        step_start = time.time()
        await _send(3, "Building taste profile")
        profile = await stack.profiler.build_profile(
            username=username, domain="all", enrich_keywords=True, max_enrich=100)
        cache.set_profile(username, "all", profile)
        cache.set_step_duration("profile", int((time.time() - step_start) * 1000))

        # Step 4: Run tonight + grab + rediscover IN PARALLEL, skip AI explanations
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

        # Step 5: Trending (fast — direct TMDB query)
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

        # Step 6: Pre-warm collections (background — avoid slow first load)
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
        _active_job = None


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/refresh")
async def start_refresh(user: TokenPayload = Depends(get_current_user)):
    """Start a background cache refresh job. Returns job_id for SSE stream."""
    global _active_job

    if _active_job and _active_job in _jobs and _jobs[_active_job]["status"] == "running":
        return {"job_id": _active_job, "status": "already_running"}

    job_id = str(uuid.uuid4())[:8]
    queue = asyncio.Queue()

    _jobs[job_id] = {
        "queue": queue,
        "status": "running",
        "started_at": time.time(),
        "username": user.username,
    }
    _active_job = job_id

    # Clean up old jobs (keep last 5)
    if len(_jobs) > 6:
        old_ids = sorted(_jobs.keys(), key=lambda k: _jobs[k].get("started_at", 0))[:-5]
        for old_id in old_ids:
            del _jobs[old_id]

    asyncio.create_task(_run_refresh(job_id, user.username))

    cache = get_cache()
    return {
        "job_id": job_id,
        "status": "started",
        "estimate_ms": cache.get_last_refresh_duration(),
    }


@router.get("/refresh/status")
async def refresh_status():
    """Current refresh state: last duration, active job, per-step timing."""
    cache = get_cache()
    return {
        "active_job": _active_job if _active_job and _active_job in _jobs and _jobs[_active_job]["status"] == "running" else None,
        "last_refresh_ms": cache.get_last_refresh_duration(),
        "last_refresh_at": cache.get_last_refresh_time(),
        "step_durations": cache.get_step_durations(),
    }


@router.get("/refresh/{job_id}/stream")
async def stream_refresh(job_id: str):
    """SSE event stream for refresh progress. Connect after POST /cache/refresh."""
    if job_id not in _jobs:
        async def not_found():
            yield "data: {\"error\": \"Job not found\"}\n\n"
        return StreamingResponse(not_found(), media_type="text/event-stream")

    queue: asyncio.Queue = _jobs[job_id]["queue"]

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60)
                yield event.to_sse()
                if event.done:
                    break
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )




@router.get("/freshness/{username}")
async def get_freshness(username: str, domain: str = "all"):
    """Per-mode cache freshness for a user. Returns ages in seconds."""
    cache = get_cache()
    ages = cache.get_all_recs_ages(username, domain)
    return {
        "username": username,
        "domain": domain,
        "modes": ages,
        "last_refresh_at": cache.get_last_refresh_time(),
        "profile_modified_at": get_override_store().get_updated_at(username),
    }
