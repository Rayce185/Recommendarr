"""Cache refresh API with SSE progress streaming.

POST /cache/refresh        — Start a background refresh job
GET  /cache/refresh/status — Current refresh state + last duration
GET  /cache/refresh/{job_id}/stream — SSE event stream for live progress
"""

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.cache import get_cache
from app.services.profile_overrides import get_override_store
from app.services.refresh_task import (
    get_jobs, get_active_job, set_active_job, run_refresh,
)

router = APIRouter(prefix="/cache", tags=["cache"])


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/refresh")
async def start_refresh(user: TokenPayload = Depends(get_current_user)):
    """Start a background cache refresh job. Returns job_id for SSE stream."""
    jobs = get_jobs()
    active = get_active_job()

    if active and active in jobs and jobs[active]["status"] == "running":
        return {"job_id": active, "status": "already_running"}

    job_id = str(uuid.uuid4())[:8]
    queue = asyncio.Queue()

    jobs[job_id] = {
        "queue": queue,
        "status": "running",
        "started_at": time.time(),
        "username": user.username,
    }
    set_active_job(job_id)

    # Clean up old jobs (keep last 5)
    if len(jobs) > 6:
        old_ids = sorted(jobs.keys(), key=lambda k: jobs[k].get("started_at", 0))[:-5]
        for old_id in old_ids:
            del jobs[old_id]

    asyncio.create_task(run_refresh(job_id, user.username))

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
    jobs = get_jobs()
    active = get_active_job()
    return {
        "active_job": active if active and active in jobs and jobs[active]["status"] == "running" else None,
        "last_refresh_ms": cache.get_last_refresh_duration(),
        "last_refresh_at": cache.get_last_refresh_time(),
        "step_durations": cache.get_step_durations(),
    }


@router.get("/refresh/{job_id}/stream")
async def stream_refresh(job_id: str):
    """SSE event stream for refresh progress. Connect after POST /cache/refresh."""
    jobs = get_jobs()
    if job_id not in jobs:
        async def not_found():
            yield "data: {\"error\": \"Job not found\"}\n\n"
        return StreamingResponse(not_found(), media_type="text/event-stream")

    queue: asyncio.Queue = jobs[job_id]["queue"]

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
