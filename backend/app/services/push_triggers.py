"""Push notification triggers — fire-and-forget helpers for event hooks.

Each function is safe to call from async context (runs push delivery
in a background thread to avoid blocking the event loop). All failures
are logged but never propagated — push is best-effort, never critical path.

Hook points:
  - scheduler.py          → notify_recs_ready()
  - vitality_scheduler.py → notify_sunset_votes_needed()
  - group_night.py        → notify_group_night_invite()
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.database import get_db
from app.models.core import User

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")


def _resolve_user_id(username: str) -> int | None:
    """Resolve username → internal User.id for push delivery."""
    db = get_db()
    try:
        row = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        return row.id if row else None
    finally:
        db.close()


def _send_safe(user_id: int, title: str, body: str, **kwargs):
    """Thread-safe push delivery — never raises."""
    try:
        from app.services.push_service import send_push
        result = send_push(user_id, title, body, **kwargs)
        if result.get("sent", 0) > 0:
            logger.info("Push sent to user %d: %s", user_id, title)
    except Exception as e:
        logger.debug("Push delivery failed for user %d: %s", user_id, e)


# ── Recommendation Refresh ───────────────────────────────────────

async def notify_recs_ready(username: str, counts: dict):
    """Notify user that scheduled recommendations are ready.

    counts: {"tonight": N, "grab": N, "rediscover": N}
    """
    user_id = _resolve_user_id(username)
    if not user_id:
        return

    total = sum(counts.values())
    if total == 0:
        return

    body = f"{total} new recommendations across {len([c for c in counts.values() if c > 0])} modes"
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor, _send_safe, user_id,
        "New Recommendations Ready", body,
    )


# ── Sunset Zone Voting ───────────────────────────────────────────

async def notify_sunset_votes_needed(transitions: dict):
    """Notify ALL subscribed users when items enter sunset zone.

    transitions: {"entered_sunset": N, "recovered": N, ...}
    """
    entered = transitions.get("entered_sunset", 0)
    if entered == 0:
        return

    try:
        from app.services.push_service import send_push_to_all
        body = (
            f"{entered} item{'s' if entered != 1 else ''} entered the sunset zone — vote to keep or kick"
        )
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor, send_push_to_all,
            "Sunset Vote Needed", body,
        )
    except Exception as e:
        logger.debug("Sunset push broadcast failed: %s", e)


# ── Group Night Invite ───────────────────────────────────────────

async def notify_group_night_invite(
    creator: str, participants: list[str], code: str, title: str | None,
):
    """Notify invited participants about a new group night session."""
    session_title = title or f"Group Night from {creator}"
    body = f"{creator} shared picks with you — tap to join"

    for username in participants:
        if username.lower() == creator.lower():
            continue  # Don't notify the creator
        user_id = _resolve_user_id(username)
        if not user_id:
            continue
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor, _send_safe, user_id,
            session_title, body,
        )
