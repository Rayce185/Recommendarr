"""Seerr client — TMDB metadata proxy + request management.

Seerr already integrates TMDB internally. Instead of hitting TMDB directly,
we use Seerr as our metadata gateway: keywords, cast/crew, ratings, trailers,
discover, trending — all through one authenticated API.

Also handles media requests (the "Worth Grabbing" → Radarr/Sonarr pipeline).
"""

import httpx
import logging
from typing import Optional

from app.clients.seerr_models import (
    SeerrMediaDetail, SeerrDiscoverResult, SeerrRequest,
    MOVIE_GENRE_MAP, TV_GENRE_MAP,
    parse_detail, parse_discover_result, resolve_genre_ids,
)

logger = logging.getLogger(__name__)


class SeerrClient:
    """Seerr API client — serves as TMDB metadata proxy and request gateway."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Authenticated GET to Seerr API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.url}/api/v1{path}",
                headers={"X-Api-Key": self.api_key},
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: dict) -> dict:
        """Authenticated POST to Seerr API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.url}/api/v1{path}",
                headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def test_connection(self) -> bool:
        """Test Seerr reachability."""
        try:
            data = await self._get("/settings/public")
            return bool(data.get("initialized"))
        except Exception:
            return False

    # ── Metadata (TMDB proxy) ────────────────────────────────────

    async def get_movie(self, tmdb_id: int) -> SeerrMediaDetail:
        """Full movie metadata including keywords, cast, crew, trailers."""
        d = await self._get(f"/movie/{tmdb_id}")
        return parse_detail(d, "movie")

    async def get_tv(self, tmdb_id: int) -> SeerrMediaDetail:
        """Full TV show metadata including keywords, cast, crew."""
        d = await self._get(f"/tv/{tmdb_id}")
        return parse_detail(d, "tv")

    async def get_detail(self, tmdb_id: int, media_type: str) -> SeerrMediaDetail:
        """Get metadata for either movie or TV by type."""
        if media_type == "tv" or media_type == "show":
            return await self.get_tv(tmdb_id)
        return await self.get_movie(tmdb_id)

    async def get_keywords(self, tmdb_id: int, media_type: str = "movie") -> list[str]:
        """Get just the keyword list for a title (lightweight call)."""
        detail = await self.get_detail(tmdb_id, media_type)
        return detail.keywords

    async def get_similar(self, tmdb_id: int, media_type: str = "movie", page: int = 1) -> list[SeerrDiscoverResult]:
        """Get similar titles via TMDB's similarity engine."""
        path = f"/movie/{tmdb_id}/similar" if media_type == "movie" else f"/tv/{tmdb_id}/similar"
        d = await self._get(path, {"page": page})
        return [parse_discover_result(r, media_type) for r in d.get("results", [])]

    async def get_recommendations_tmdb(self, tmdb_id: int, media_type: str = "movie", page: int = 1) -> list[SeerrDiscoverResult]:
        """Get TMDB's own recommendations for a title."""
        path = f"/movie/{tmdb_id}/recommendations" if media_type == "movie" else f"/tv/{tmdb_id}/recommendations"
        d = await self._get(path, {"page": page})
        return [parse_discover_result(r, media_type) for r in d.get("results", [])]

    # ── Discover / Trending ──────────────────────────────────────

    async def get_trending(self, page: int = 1) -> list[SeerrDiscoverResult]:
        """Get globally trending movies + TV."""
        d = await self._get("/discover/trending", {"page": page})
        return [
            parse_discover_result(r, r.get("mediaType", "movie"))
            for r in d.get("results", [])
        ]

    async def discover_movies(self, page: int = 1, genre: int | None = None,
                               sort_by: str = "popularity.desc",
                               year: int | None = None,
                               keywords: str | None = None) -> list[SeerrDiscoverResult]:
        """TMDB discover endpoint for movies with filters."""
        params = {"page": page, "sortBy": sort_by}
        if genre:
            params["genre"] = str(genre)
        if year:
            params["primaryReleaseDateGte"] = f"{year}-01-01"
            params["primaryReleaseDateLte"] = f"{year}-12-31"
        if keywords:
            params["keywords"] = keywords
        d = await self._get("/discover/movies", params)
        return [parse_discover_result(r, "movie") for r in d.get("results", [])]

    async def discover_tv(self, page: int = 1, genre: int | None = None,
                           sort_by: str = "popularity.desc") -> list[SeerrDiscoverResult]:
        """TMDB discover endpoint for TV shows with filters."""
        params = {"page": page, "sortBy": sort_by}
        if genre:
            params["genre"] = str(genre)
        d = await self._get("/discover/tv", params)
        return [parse_discover_result(r, "tv") for r in d.get("results", [])]

    async def search(self, query: str, page: int = 1) -> list[SeerrDiscoverResult]:
        """Search movies + TV by text query."""
        from urllib.parse import quote
        # Seerr requires %20 encoding for spaces (rejects + encoding)
        encoded_query = quote(query, safe='')
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.url}/api/v1/search?query={encoded_query}&page={page}&language=en",
                headers={"X-Api-Key": self.api_key},
            )
            resp.raise_for_status()
            d = resp.json()
        return [
            parse_discover_result(r, r.get("mediaType", "movie"))
            for r in d.get("results", [])
        ]

    # ── Genre lists ──────────────────────────────────────────────

    async def get_movie_genres(self) -> list[dict]:
        """Get TMDB movie genre list via Seerr."""
        return await self._get("/genres/movie")

    async def get_tv_genres(self) -> list[dict]:
        """Get TMDB TV genre list via Seerr."""
        return await self._get("/genres/tv")

    # ── Requests (Worth Grabbing → Radarr/Sonarr) ───────────────

    async def request_movie(self, tmdb_id: int) -> SeerrRequest:
        """Submit a movie request through Seerr → Radarr."""
        d = await self._post("/request", {
            "mediaId": tmdb_id,
            "mediaType": "movie",
        })
        return SeerrRequest(
            request_id=d.get("id", 0),
            tmdb_id=tmdb_id,
            media_type="movie",
            status=d.get("status", 1),
            requested_by=str(d.get("requestedBy", {}).get("displayName", "")),
            created_at=d.get("createdAt"),
        )

    async def request_tv(self, tmdb_id: int, seasons: list[int] | None = None) -> SeerrRequest:
        """Submit a TV request through Seerr → Sonarr.

        If seasons is None, requests all seasons.
        """
        body = {"mediaId": tmdb_id, "mediaType": "tv"}
        if seasons:
            body["seasons"] = seasons
        d = await self._post("/request", body)
        return SeerrRequest(
            request_id=d.get("id", 0),
            tmdb_id=tmdb_id,
            media_type="tv",
            status=d.get("status", 1),
            requested_by=str(d.get("requestedBy", {}).get("displayName", "")),
            created_at=d.get("createdAt"),
        )

    async def get_requests(self, take: int = 20, skip: int = 0,
                           status: str = "all") -> list[SeerrRequest]:
        """List existing requests with pagination."""
        params = {"take": take, "skip": skip}
        if status != "all":
            params["filter"] = status  # "pending", "approved", "declined", "available"
        d = await self._get("/request", params)
        results = []
        for r in d.get("results", []):
            media = r.get("media", {})
            results.append(SeerrRequest(
                request_id=r.get("id", 0),
                tmdb_id=media.get("tmdbId", 0),
                media_type=r.get("type", "movie"),
                status=r.get("status", 1),
                requested_by=str(r.get("requestedBy", {}).get("displayName", "")),
                created_at=r.get("createdAt"),
            ))
        return results

    def resolve_genre_ids(self, genre_ids: list[int], media_type: str = "movie") -> list[str]:
        """Convert TMDB genre IDs to names."""
        return resolve_genre_ids(genre_ids, media_type)
