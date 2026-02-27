"""Tautulli client — IWatchHistoryProvider implementation.

Handles: watch history retrieval, most-watched queries.
Supports both API polling and webhook-based real-time ingestion.
"""

import httpx
from datetime import datetime
from typing import Optional

from app.clients.base import IWatchHistoryProvider, WatchEvent


class TautulliClient(IWatchHistoryProvider):
    """Tautulli implementation of IWatchHistoryProvider."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key

    async def _get(self, cmd: str, params: dict | None = None) -> dict:
        """Make authenticated GET request to Tautulli API v2."""
        all_params = {
            "apikey": self.api_key,
            "cmd": cmd,
            **(params or {}),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.url}/api/v2",
                params=all_params,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", {}).get("data", {})

    # ── IWatchHistoryProvider implementation ──────────────────────

    async def get_history(
        self,
        user_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[WatchEvent]:
        """Pull watch history from Tautulli.

        Tautulli's get_history supports pagination with start/length.
        We paginate until we hit the limit or run out of records.
        """
        events = []
        page_size = min(limit, 200)  # Tautulli max per page
        start = 0

        while len(events) < limit:
            params: dict = {
                "length": page_size,
                "start": start,
                "order_column": "date",
                "order_dir": "desc",
            }
            if user_id:
                params["user_id"] = user_id

            data = await self._get("get_history", params)
            records = data.get("data", [])

            if not records:
                break

            for r in records:
                event = self._parse_history_record(r)

                # Filter by date if specified
                if since and event.started_at and event.started_at < since:
                    return events  # Records are ordered desc, so we're done

                events.append(event)

                if len(events) >= limit:
                    break

            start += page_size

            # Tautulli returns total count — check if we've exhausted all records
            total = data.get("recordsFiltered", 0) or data.get("recordsTotal", 0)
            if start >= total:
                break

        return events

    async def get_most_watched(self, user_id: str, limit: int = 50) -> list[WatchEvent]:
        """Get most-watched items for a user via Tautulli's get_home_stats."""
        # Use get_history and aggregate by item — Tautulli doesn't have
        # a direct "most watched" per user endpoint with full detail
        all_history = await self.get_history(user_id=user_id, limit=5000)

        # Aggregate by media key
        by_key: dict[str, WatchEvent] = {}
        for event in all_history:
            key = event.item_key
            if key in by_key:
                by_key[key].watch_count += 1
                # Keep highest completion
                if event.completion_pct > by_key[key].completion_pct:
                    by_key[key].completion_pct = event.completion_pct
            else:
                by_key[key] = event

        # Sort by watch count desc
        sorted_events = sorted(by_key.values(), key=lambda e: e.watch_count, reverse=True)
        return sorted_events[:limit]

    async def supports_webhooks(self) -> bool:
        """Tautulli supports webhooks via notification agents."""
        return True

    async def test_connection(self) -> bool:
        """Test Tautulli reachability."""
        try:
            data = await self._get("arnold")
            return True  # arnold returns a random Arnold quote — if we got here, it works
        except Exception:
            return False

    # ── Tautulli-specific methods ────────────────────────────────

    async def get_users(self) -> list[dict]:
        """Get Tautulli user list with IDs and names."""
        data = await self._get("get_users")
        return data if isinstance(data, list) else []

    async def get_user_watch_time_stats(self, user_id: str) -> dict:
        """Get aggregated watch time stats for a user."""
        data = await self._get("get_user_watch_time_stats", {"user_id": user_id})
        return data if isinstance(data, list) else data

    async def get_recently_added(self, count: int = 25) -> list[dict]:
        """Get recently added items on the server."""
        data = await self._get("get_recently_added", {"count": count})
        return data.get("recently_added", []) if isinstance(data, dict) else []

    # ── Webhook payload parsing ──────────────────────────────────

    @staticmethod
    def parse_webhook_payload(body: dict) -> Optional[WatchEvent]:
        """Parse a Tautulli webhook payload into a WatchEvent.

        Expected webhook JSON format (configured in Tautulli notification agent):
        {
            "event_type": "watched" | "play" | "stop" | "pause" | "resume",
            "user_id": "12345",
            "username": "Ray",
            "rating_key": "56789",
            "title": "Oppenheimer",
            "year": 2023,
            "media_type": "movie",
            "duration": 10800,
            "view_offset": 9500,
            "progress_percent": 88,
            "tmdb_id": "872585",
        }
        """
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
            started_at=datetime.now(),
            duration_seconds=view_offset,
            total_duration_seconds=duration,
            completion_pct=progress,
            watch_count=1,
        )

    async def resolve_tmdb_id(self, rating_key: str, media_type: str = "movie") -> int | None:
        """Resolve a Plex rating_key to a TMDB ID via Tautulli's get_metadata.

        For episodes: uses grandparent_guids (the show's TMDB ID).
        For movies: uses guids directly.
        """
        try:
            data = await self._get("get_metadata", {"rating_key": rating_key})
            if not data:
                return None

            # For episodes, we want the show's TMDB ID
            if media_type == "episode":
                guids = data.get("grandparent_guids", [])
            else:
                guids = data.get("guids", [])

            for g in guids:
                if isinstance(g, str) and g.startswith("tmdb://"):
                    try:
                        return int(g.replace("tmdb://", ""))
                    except ValueError:
                        pass
        except Exception:
            pass
        return None

    async def resolve_tmdb_ids_batch(
        self, rating_keys: list[tuple[str, str]]
    ) -> dict[str, int | None]:
        """Batch resolve rating_keys to TMDB IDs.

        Args:
            rating_keys: list of (rating_key, media_type) tuples

        Returns:
            {rating_key: tmdb_id} mapping
        """
        results = {}
        for key, mtype in rating_keys:
            results[key] = await self.resolve_tmdb_id(key, mtype)
        return results

    # ── Internal helpers ─────────────────────────────────────────

    def _parse_history_record(self, r: dict) -> WatchEvent:
        """Parse a single Tautulli history record."""
        duration = int(r.get("duration", 0))
        total = int(r.get("full_duration", 0) or r.get("duration", 0))
        completion = (duration / total * 100) if total > 0 else 0.0

        # Extract TMDB ID from GUIDs if available
        tmdb_id = None
        guids = r.get("guids", [])
        if isinstance(guids, list):
            for g in guids:
                if isinstance(g, str) and g.startswith("tmdb://"):
                    try:
                        tmdb_id = int(g.replace("tmdb://", ""))
                    except ValueError:
                        pass

        # Tautulli also provides grandparent info for episodes
        media_type = r.get("media_type", "movie")
        if media_type == "episode":
            media_type = "episode"

        started = None
        if r.get("started"):
            try:
                started = datetime.fromtimestamp(int(r["started"]))
            except (ValueError, TypeError):
                pass

        return WatchEvent(
            user_id=str(r.get("user_id", "")),
            item_key=str(r.get("rating_key", "")),
            tmdb_id=tmdb_id,
            media_type=media_type,
            started_at=started,
            duration_seconds=duration,
            total_duration_seconds=total,
            completion_pct=round(completion, 1),
            watch_count=1,  # Each history record is one watch
            user_rating=None,
        )
