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
    """Execute cache refresh steps and push progress to SSE queue."""
    global _active_job
    job = _jobs[job_id]
    queue: asyncio.Queue = job["queue"]
    start = time.time()
    cache = get_cache()
    stack = get_stack()

    steps = [
        ("Clearing stale caches", "clear"),
        ("Loading movie library (Radarr)", "radarr"),
        ("Loading TV library (Sonarr)", "sonarr_tv"),
        ("Loading anime library (Sonarr Anime)", "sonarr_anime"),
        ("Building taste profile", "profile"),
        ("Generating Watch Tonight", "tonight"),
        ("Generating Worth Grabbing", "grab"),
        ("Generating Rediscover", "rediscover"),
        ("Fetching Trending", "trending"),
    ]
    total = len(steps)

    try:
        for i, (label, step_key) in enumerate(steps):
            step_start = time.time()
            elapsed = int((time.time() - start) * 1000)
            await queue.put(RefreshStep(i + 1, total, label, elapsed))

            try:
                if step_key == "clear":
                    cache.invalidate_all()

                elif step_key == "radarr":
                    movies = await stack.radarr.get_all_movies()
                    logger.info(f"Refresh: loaded {len(movies)} movies from Radarr")

                elif step_key == "sonarr_tv":
                    series = await stack.sonarr_tv.get_all_series()
                    logger.info(f"Refresh: loaded {len(series)} TV series from Sonarr")

                elif step_key == "sonarr_anime":
                    anime = await stack.sonarr_anime.get_all_series()
                    logger.info(f"Refresh: loaded {len(anime)} anime from Sonarr Anime")

                elif step_key == "profile":
                    await stack.profiler.build_profile(username=username, domain="all", enrich_keywords=True, max_enrich=100)

                elif step_key == "tonight":
                    from app.services.recommender import RecommendationRequest
                    req = RecommendationRequest(username=username, mode="tonight", domain="all", limit=20)
                    await stack.engine.recommend(req)

                elif step_key == "grab":
                    from app.services.recommender import RecommendationRequest
                    req = RecommendationRequest(username=username, mode="grab", domain="all", limit=20)
                    await stack.engine.recommend(req)

                elif step_key == "rediscover":
                    from app.services.recommender import RecommendationRequest
                    req = RecommendationRequest(username=username, mode="rediscover", domain="all", limit=20)
                    await stack.engine.recommend(req)

                elif step_key == "trending":
                    await stack.seerr.get_trending(page=1)

            except Exception as e:
                logger.warning(f"Refresh step '{step_key}' failed: {e}")
                # Continue to next step — partial refresh is better than none

            step_ms = int((time.time() - step_start) * 1000)
            cache.set_step_duration(step_key, step_ms)

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
