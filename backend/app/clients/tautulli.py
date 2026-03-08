"""Tautulli client — IWatchHistoryProvider implementation.

Handles: watch history retrieval, most-watched queries.
Supports both API polling and webhook-based real-time ingestion.
"""

import httpx
from datetime import datetime, timezone
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

    async def get_plays_by_hourofday(self, user_id: str = None) -> list[int]:
        """Get total play counts by hour of day (0-23) in server time.

        Returns a 24-element list where index = hour, value = total plays.
        If user_id is provided, returns data for that user only.
        """
        params = {}
        if user_id:
            params["user_id"] = user_id
        data = await self._get("get_plays_by_hourofday", params)
        series = data.get("series", [])
        cats = data.get("categories", [])
        totals = [0] * max(len(cats), 24)
        for s in series:
            for i, v in enumerate(s.get("data", [])):
                totals[i] += v
        return totals[:24]

    async def get_recently_added(self, count: int = 25) -> list[dict]:
        """Get recently added items on the server."""
        data = await self._get("get_recently_added", {"count": count})
        return data.get("recently_added", []) if isinstance(data, dict) else []

    # ── Webhook payload parsing ──────────────────────────────────

    async def resolve_tmdb_id(self, rating_key: str, media_type: str = "movie") -> int | None:
        """Resolve a Plex rating_key to a TMDB ID via Tautulli's get_metadata.

        For episodes: uses grandparent_guids (the show's TMDB ID).
        For movies: uses guids directly.
        """
        try:
            data = await self._get("get_metadata", {"rating_key": rating_key})
            if not data:
                return None

            # Try guids first (works for movies and shows), then grandparent_guids (episodes)
            guids = data.get("guids", []) or []
            if not guids and media_type == "episode":
                guids = data.get("grandparent_guids", []) or []

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
        """Batch resolve rating_keys to TMDB IDs (parallel with concurrency limit).

        Args:
            rating_keys: list of (rating_key, media_type) tuples

        Returns:
            {rating_key: tmdb_id} mapping
        """
        import asyncio
        results = {}
        sem = asyncio.Semaphore(10)

        async def _resolve(key, mtype):
            async with sem:
                return key, await self.resolve_tmdb_id(key, mtype)

        tasks = [_resolve(k, m) for k, m in rating_keys]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        for r in done:
            if isinstance(r, tuple):
                results[r[0]] = r[1]
        return results

    @staticmethod
    def parse_webhook_payload(body: dict):
        """Parse a Tautulli webhook payload into a WatchEvent."""
        from app.clients.tautulli_parsers import parse_webhook_payload
        return parse_webhook_payload(body)

    def _parse_history_record(self, r: dict):
        """Parse a single Tautulli history record."""
        from app.clients.tautulli_parsers import parse_history_record
        return parse_history_record(r)
