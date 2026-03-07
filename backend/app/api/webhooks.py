"""Webhook receivers for real-time event ingestion."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.clients.tautulli_parsers import parse_webhook_payload
from app.database import get_db
from app.models import WatchHistory, User
from app.services.factory import get_stack, resolve_username
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_user_db_id(db, username: str) -> int | None:
    """Get internal user ID from username."""
    return db.execute(
        select(User.id).where(User.username == username)
    ).scalar_one_or_none()


@router.post("/webhook/tautulli")
async def tautulli_webhook(request: Request):
    """Tautulli sends play/stop/pause/resume/watched events here.

    Configure in Tautulli: Settings > Notification Agents > Webhook
    URL: http://<recommendarr>:30800/api/v1/webhook/tautulli
    Triggers: Watched, Play, Stop
    JSON body should include: user_id, rating_key, media_type,
                              duration, view_offset, progress_percent, tmdb_id
    """
    body = await request.json()
    event_type = body.get("event_type", "unknown")

    event = parse_webhook_payload(body)
    if event is None:
        return {"status": "ignored", "reason": f"unhandled event: {event_type}"}

    # Only ingest completed watches (watched event or stop with >=75%)
    should_ingest = (
        event_type == "watched"
        or (event_type == "stop" and event.completion_pct >= 75)
    )

    if not should_ingest:
        logger.debug(f"webhook: skip {event_type} for user {event.user_id} ({event.completion_pct}%)")
        return {"status": "ack", "event_type": event_type, "ingested": False}

    # Resolve username
    username = resolve_username(event.user_id)

    # Resolve TMDB ID if missing
    tmdb_id = event.tmdb_id
    if not tmdb_id and event.item_key:
        try:
            stack = get_stack()
            tmdb_id = await stack.tautulli.resolve_tmdb_id(
                event.item_key, event.media_type
            )
        except Exception as e:
            logger.warning(f"webhook: tmdb resolve failed for {event.item_key}: {e}")

    if not tmdb_id:
        logger.warning(f"webhook: no tmdb_id for rating_key={event.item_key}, skipping")
        return {"status": "error", "reason": "no_tmdb_id", "rating_key": event.item_key}

    # Upsert into WatchHistory
    try:
        db = get_db()
        user_id = _resolve_user_db_id(db, username)
        if user_id is None:
            db.close()
            return {"status": "error", "reason": f"unknown user: {username}"}

        # Check for existing entry (same user + tmdb_id)
        existing = db.execute(
            select(WatchHistory).where(
                and_(
                    WatchHistory.user_id == user_id,
                    WatchHistory.tmdb_id == tmdb_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.watch_count += 1
            existing.duration_seconds = event.duration_seconds or existing.duration_seconds
            existing.completion_pct = max(event.completion_pct, existing.completion_pct or 0)
            existing.started_at = event.started_at or existing.started_at
            logger.info(f"webhook: updated watch #{existing.id} for {username} tmdb={tmdb_id} (count={existing.watch_count})")
        else:
            entry = WatchHistory(
                user_id=user_id,
                tmdb_id=tmdb_id,
                media_type=event.media_type,
                plex_rating_key=event.item_key,
                started_at=event.started_at,
                duration_seconds=event.duration_seconds,
                total_duration_seconds=event.total_duration_seconds,
                completion_pct=event.completion_pct,
                watch_count=1,
            )
            db.add(entry)
            logger.info(f"webhook: new watch for {username} tmdb={tmdb_id} ({event.media_type})")

        db.commit()
        db.close()
        return {"status": "ok", "event_type": event_type, "ingested": True, "tmdb_id": tmdb_id, "user": username}

    except Exception as e:
        logger.error(f"webhook: db error: {e}")
        return {"status": "error", "reason": str(e)}


@router.post("/webhook/radarr")
async def radarr_webhook(request: Request):
    """Radarr sends grab/download/rename events here."""
    body = await request.json()
    event_type = body.get("eventType", "unknown")
    title = body.get("movie", {}).get("title", "unknown")
    tmdb_id = body.get("movie", {}).get("tmdbId")

    logger.info(f"webhook/radarr: {event_type} — {title} (tmdb={tmdb_id})")

    return {"status": "received", "event_type": event_type, "title": title, "tmdb_id": tmdb_id}


@router.post("/webhook/sonarr")
async def sonarr_webhook(request: Request):
    """Sonarr sends grab/download/rename events here."""
    body = await request.json()
    event_type = body.get("eventType", "unknown")
    title = body.get("series", {}).get("title", "unknown")
    tvdb_id = body.get("series", {}).get("tvdbId")

    logger.info(f"webhook/sonarr: {event_type} — {title} (tvdb={tvdb_id})")

    return {"status": "received", "event_type": event_type, "title": title, "tvdb_id": tvdb_id}
