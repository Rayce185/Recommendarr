"""Scheduled refresh — per-user timezone-aware auto-refresh.

Runs as a background asyncio task. Checks every 5 minutes whether
any user's scheduled refresh window has arrived (based on their local time).

Design:
  - Each user can enable auto-refresh with a timezone + hour
  - Scheduler converts current UTC → user's local time
  - If local hour matches schedule AND last_run was before today's window → fire
  - Reuses existing refresh logic (parallel modes, skip AI explanations)
  - Logs results to RefreshSchedule.last_run_at / last_run_ms / last_error
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select

from app.database import get_db
from app.models.tables import RefreshSchedule

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 300  # 5 minutes between schedule checks


class RefreshScheduler:
    """Background scheduler for per-user auto-refresh."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self):
        """Start the background scheduler loop."""
        if self._task and not self._task.done():
            logger.debug("Scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Refresh scheduler started (check every 5 min)")

    async def stop(self):
        """Gracefully stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Refresh scheduler stopped")

    async def _loop(self):
        """Main loop — check schedules every CHECK_INTERVAL seconds."""
        await asyncio.sleep(30)  # Let startup warming finish first
        while self._running:
            try:
                await self._check_schedules()
            except Exception as e:
                logger.error(f"Scheduler check failed: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

    async def _check_schedules(self):
        """Check all enabled schedules and fire any that are due."""
        now_utc = datetime.now(timezone.utc)

        with get_db() as db:
            schedules = db.execute(
                select(RefreshSchedule).where(RefreshSchedule.enabled == True)
            ).scalars().all()

        if not schedules:
            return

        for sched in schedules:
            try:
                if self._is_due(sched, now_utc):
                    logger.info(f"Scheduled refresh due for {sched.username} "
                                f"(hour={sched.hour:02d}:{sched.minute:02d} server time)")
                    await self._run_user_refresh(sched)
            except Exception as e:
                logger.warning(f"Schedule check failed for {sched.username}: {e}")
                self._record_error(sched.username, str(e))

    def _is_due(self, sched: RefreshSchedule, now_utc: datetime) -> bool:
        """Check if scheduled refresh is due. All times are server time.

        Tautulli data is server time, quiet hours are server time,
        scheduler runs in server time. No timezone conversion.
        """
        import os
        try:
            from zoneinfo import ZoneInfo
            server_tz = ZoneInfo(os.environ.get("TZ", "UTC"))
            now_server = now_utc.astimezone(server_tz)
        except Exception:
            now_server = now_utc

        today_scheduled = now_server.replace(
            hour=sched.hour, minute=sched.minute, second=0, microsecond=0
        )

        if now_server < today_scheduled:
            return False

        # 2-hour catch-up window
        if (now_server - today_scheduled).total_seconds() > 7200:
            return False

        if sched.last_run_at:
            try:
                last = sched.last_run_at.astimezone(server_tz) if sched.last_run_at.tzinfo else sched.last_run_at
            except Exception:
                last = sched.last_run_at
            if last >= today_scheduled:
                return False

        return True

    async def _run_user_refresh(self, sched: RefreshSchedule):
        """Execute refresh for a single user (reuses engine logic)."""
        from app.services.factory import get_stack
        from app.services.cache import get_cache
        from app.services.recommender import RecommendationRequest
        from app.api.recommendations import _rec_to_dict
        from app.services.feedback import get_feedback_store

        username = sched.username
        start = time.time()
        stack = get_stack()
        cache = get_cache()

        try:
            # 1. Invalidate user's caches
            cache.invalidate_user(username)

            # 2. Rebuild taste profile
            profile = await stack.profiler.build_profile(
                username=username, domain="all",
                enrich_keywords=True, max_enrich=100)
            cache.set_profile(username, "all", profile)

            # 3. Refresh library candidates (shared cache, only if stale)
            if cache.get_library("all") is None:
                await stack.engine._get_library_candidates("all")

            # 4. Run all modes in parallel, skip AI explanations
            async def _run_mode(mode):
                try:
                    req = RecommendationRequest(
                        username=username, mode=mode, domain="all",
                        limit=30, skip_explanations=True)
                    recs = await stack.engine.recommend(req)
                    # Cache formatted results
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
                except Exception as e:
                    logger.warning(f"Scheduled {mode} failed for {username}: {e}")
                    return 0

            counts = await asyncio.gather(
                _run_mode("tonight"),
                _run_mode("grab"),
                _run_mode("rediscover"),
            )

            # 5. Refresh collections
            try:
                from app.services.collections import CollectionService
                if not hasattr(stack, "_collection_svc") or stack._collection_svc is None:
                    stack._collection_svc = CollectionService(stack.tmdb, stack.radarr, stack.tautulli)
                colls = await stack._collection_svc.get_user_collections(username)
                coll_data = []
                for c in colls:
                    coll_data.append({
                        "collection_id": c.collection_id, "name": c.name,
                        "poster_url": c.poster_url, "backdrop_url": c.backdrop_url,
                        "total_parts": c.total_parts, "watched_count": c.watched_count,
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
                    })
                cache.set_collections(username, coll_data)
            except Exception as e:
                logger.debug(f"Scheduled collection refresh skipped for {username}: {e}")

            elapsed_ms = int((time.time() - start) * 1000)
            self._record_success(username, elapsed_ms)
            logger.info(f"Scheduled refresh done for {username}: "
                        f"tonight={counts[0]}, grab={counts[1]}, rediscover={counts[2]} "
                        f"in {elapsed_ms}ms")

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            self._record_error(username, str(e))
            logger.error(f"Scheduled refresh failed for {username}: {e} ({elapsed_ms}ms)")

    def _record_success(self, username: str, elapsed_ms: int):
        """Update last_run in DB."""
        try:
            with get_db() as db:
                sched = db.execute(
                    select(RefreshSchedule).where(RefreshSchedule.username == username)
                ).scalar_one_or_none()
                if sched:
                    sched.last_run_at = datetime.now(timezone.utc)
                    sched.last_run_ms = elapsed_ms
                    sched.last_error = None
                    sched.updated_at = datetime.now(timezone.utc)
                    db.commit()
        except Exception as e:
            logger.debug(f"Failed to record success for {username}: {e}")

    def _record_error(self, username: str, error: str):
        """Update last_error in DB."""
        try:
            with get_db() as db:
                sched = db.execute(
                    select(RefreshSchedule).where(RefreshSchedule.username == username)
                ).scalar_one_or_none()
                if sched:
                    sched.last_run_at = datetime.now(timezone.utc)
                    sched.last_error = error[:500]
                    sched.updated_at = datetime.now(timezone.utc)
                    db.commit()
        except Exception as e:
            logger.debug(f"Failed to record error for {username}: {e}")


# ── Singleton ────────────────────────────────────────────────────
_scheduler: Optional[RefreshScheduler] = None


def get_scheduler() -> RefreshScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = RefreshScheduler()
    return _scheduler
