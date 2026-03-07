"""Tautulli payload parsers — webhook and history record parsing.

Pure data transformation functions split from tautulli.py for §7.7.
"""

from datetime import datetime, timezone
from typing import Optional

from app.clients.base import WatchEvent


def parse_webhook_payload(body: dict) -> Optional[WatchEvent]:
    """Parse a Tautulli webhook payload into a WatchEvent."""
    event_type = body.get("event_type", "")
    if event_type not in ("watched", "play", "stop", "pause", "resume"):
        return None

    duration = int(body.get("duration", 0))
    view_offset = int(body.get("view_offset", 0))
    progress = float(body.get("progress_percent", 0))

    tmdb_id = None
    if body.get("tmdb_id"):
        try:
            tmdb_id = int(body["tmdb_id"])
        except (ValueError, TypeError):
            pass

    return WatchEvent(
        user_id=str(body.get("user_id", "")),
        item_key=str(body.get("rating_key", "")),
        tmdb_id=tmdb_id,
        media_type=body.get("media_type", "movie"),
        started_at=datetime.now(timezone.utc),
        duration_seconds=view_offset,
        total_duration_seconds=duration,
        completion_pct=progress,
        watch_count=1,
    )


def parse_history_record(r: dict) -> WatchEvent:
    """Parse a single Tautulli history record."""
    duration = int(r.get("duration", 0) or r.get("play_duration", 0))
    completion = float(r.get("percent_complete", 0))

    tmdb_id = None
    guids = r.get("guids", [])
    if isinstance(guids, list):
        for g in guids:
            if isinstance(g, str) and g.startswith("tmdb://"):
                try:
                    tmdb_id = int(g.replace("tmdb://", ""))
                except ValueError:
                    pass

    media_type = r.get("media_type", "movie")
    rating_key = str(r.get("rating_key", ""))
    if media_type == "episode":
        grandparent_key = r.get("grandparent_rating_key")
        if grandparent_key:
            rating_key = str(grandparent_key)

    started = None
    if r.get("started"):
        try:
            started = datetime.fromtimestamp(int(r["started"]), tz=timezone.utc)
        except (ValueError, TypeError):
            pass

    return WatchEvent(
        user_id=str(r.get("user_id", "")),
        item_key=rating_key,
        tmdb_id=tmdb_id,
        media_type=media_type,
        started_at=started,
        duration_seconds=duration,
        total_duration_seconds=duration,
        completion_pct=round(completion, 1),
        watch_count=1,
        user_rating=None,
    )
