"""TMDB client — metadata fetching, caching, and trailer lookup.

Handles: movie/show details, genres, cast/crew, keywords, trailers,
similar titles, and regional trending data for World Cinema Map.
"""

import httpx
from datetime import datetime, timezone
from typing import Optional


class TmdbClient:
    """The Movie Database API v3 client."""

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p"

    def __init__(self, api_key: str, language: str = "en-US"):
        self.api_key = api_key
        self.language = language
        # Detect auth mode: JWT (v4 bearer) vs plain key (v3 query param)
        self._is_bearer = api_key.startswith("eyJ")

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Make authenticated GET request to TMDB.

        Supports both v3 (api_key query param) and v4 (Bearer token header).
        v4 bearer tokens work with v3 endpoints via Authorization header.
        """
        all_params = {"language": self.language, **(params or {})}
        headers = {}

        if self._is_bearer:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            all_params["api_key"] = self.api_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.BASE_URL}{path}", params=all_params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # ── Movie details ────────────────────────────────────────────

    async def get_movie(self, tmdb_id: int) -> dict:
        """Full movie details with credits, keywords, videos, similar."""
        data = await self._get(
            f"/movie/{tmdb_id}",
            {"append_to_response": "credits,keywords,videos,similar,external_ids"},
        )
        return self._normalize_movie(data)

    async def get_movie_basic(self, tmdb_id: int) -> dict:
        """Lightweight movie fetch — no appended data."""
        data = await self._get(f"/movie/{tmdb_id}")
        return self._normalize_movie(data)

    # ── TV show details ──────────────────────────────────────────

    async def get_show(self, tmdb_id: int) -> dict:
        """Full TV show details with credits, keywords, videos, similar."""
        data = await self._get(
            f"/tv/{tmdb_id}",
            {"append_to_response": "credits,keywords,videos,similar,external_ids"},
        )
        return self._normalize_show(data)

    # ── Search ───────────────────────────────────────────────────

    async def search_movie(self, query: str, year: Optional[int] = None) -> list[dict]:
        """Search for movies by title."""
        params = {"query": query}
        if year:
            params["year"] = year
        data = await self._get("/search/movie", params)
        return data.get("results", [])

    async def search_tv(self, query: str) -> list[dict]:
        """Search for TV shows by title."""
        data = await self._get("/search/tv", {"query": query})
        return data.get("results", [])

    async def search_multi(self, query: str) -> list[dict]:
        """Search movies + TV + people in one call."""
        data = await self._get("/search/multi", {"query": query})
        return data.get("results", [])

    # ── Discovery / Trending ─────────────────────────────────────

    async def get_trending(self, media_type: str = "all", window: str = "week") -> list[dict]:
        """Get globally trending content."""
        data = await self._get(f"/trending/{media_type}/{window}")
        return data.get("results", [])

    async def get_regional_trending(self, region: str, media_type: str = "movie") -> list[dict]:
        """Get trending content for a specific region (World Cinema Map)."""
        data = await self._get(
            f"/trending/{media_type}/week",
            {"region": region},
        )
        return data.get("results", [])

    async def discover_movies(self, **kwargs) -> list[dict]:
        """Discover movies with filters (genres, year, rating, etc.)."""
        data = await self._get("/discover/movie", kwargs)
        return data.get("results", [])

    async def discover_tv(self, **kwargs) -> list[dict]:
        """Discover TV shows with filters."""
        data = await self._get("/discover/tv", kwargs)
        return data.get("results", [])

    # ── Upcoming releases (Coming Soon) ──────────────────────────

    async def get_upcoming_movies(self, region: str = "US", page: int = 1) -> list[dict]:
        """Movies with upcoming release dates."""
        data = await self._get("/movie/upcoming", {"region": region, "page": page})
        return data.get("results", [])

    # ── Genre lists ──────────────────────────────────────────────

    async def get_movie_genres(self) -> dict[int, str]:
        """Get {id: name} mapping for movie genres."""
        data = await self._get("/genre/movie/list")
        return {g["id"]: g["name"] for g in data.get("genres", [])}

    async def get_tv_genres(self) -> dict[int, str]:
        """Get {id: name} mapping for TV genres."""
        data = await self._get("/genre/tv/list")
        return {g["id"]: g["name"] for g in data.get("genres", [])}

    # ── IMDB → TMDB resolution ───────────────────────────────────

    async def find_by_imdb(self, imdb_id: str) -> Optional[dict]:
        """Resolve an IMDB ID to TMDB metadata."""
        data = await self._get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        movies = data.get("movie_results", [])
        if movies:
            return {"tmdb_id": movies[0]["id"], "media_type": "movie"}
        shows = data.get("tv_results", [])
        if shows:
            return {"tmdb_id": shows[0]["id"], "media_type": "tv"}
        return None

    # ── Test connection ──────────────────────────────────────────

    async def test_connection(self) -> bool:
        """Test TMDB API key validity."""
        try:
            await self._get("/configuration")
            return True
        except Exception:
            return False

    # ── Normalization helpers ────────────────────────────────────

    def _normalize_movie(self, data: dict) -> dict:
        """Normalize TMDB movie response into our standard schema."""
        trailer_key = self._extract_trailer_key(data.get("videos", {}))

        # Cast/crew extraction — top 10 cast, director, writers
        credits = data.get("credits", {})
        cast = [
            {"id": c["id"], "name": c["name"], "character": c.get("character", ""), "order": c.get("order", 99)}
            for c in credits.get("cast", [])[:10]
        ]
        crew_notable = [
            {"id": c["id"], "name": c["name"], "job": c["job"]}
            for c in credits.get("crew", [])
            if c.get("job") in ("Director", "Screenplay", "Writer", "Story")
        ]

        # Keywords
        keywords = [k["name"] for k in data.get("keywords", {}).get("keywords", [])]

        # Similar movie IDs
        similar_ids = [s["id"] for s in data.get("similar", {}).get("results", [])[:20]]

        return {
            "tmdb_id": data["id"],
            "media_type": "movie",
            "title": data.get("title", ""),
            "original_title": data.get("original_title", ""),
            "year": int(data["release_date"][:4]) if data.get("release_date") else None,
            "genres": {g["id"]: g["name"] for g in data.get("genres", [])},
            "keywords": keywords,
            "cast_crew": {"cast": cast, "crew": crew_notable},
            "overview": data.get("overview", ""),
            "vote_average": data.get("vote_average"),
            "popularity": data.get("popularity"),
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "trailer_key": trailer_key,
            "runtime_minutes": data.get("runtime"),
            "original_language": data.get("original_language"),
            "production_countries": [c["iso_3166_1"] for c in data.get("production_countries", [])],
            "similar_ids": similar_ids,
            "imdb_id": data.get("external_ids", {}).get("imdb_id") or data.get("imdb_id"),
        }

    def _normalize_show(self, data: dict) -> dict:
        """Normalize TMDB TV show response into our standard schema."""
        trailer_key = self._extract_trailer_key(data.get("videos", {}))

        credits = data.get("credits", {})
        cast = [
            {"id": c["id"], "name": c["name"], "character": c.get("character", ""), "order": c.get("order", 99)}
            for c in credits.get("cast", [])[:10]
        ]
        crew_notable = [
            {"id": c["id"], "name": c["name"], "job": c["job"]}
            for c in credits.get("crew", [])
            if c.get("job") in ("Executive Producer", "Creator", "Showrunner")
        ]

        keywords = [k["name"] for k in data.get("keywords", {}).get("results", [])]
        similar_ids = [s["id"] for s in data.get("similar", {}).get("results", [])[:20]]

        first_air = data.get("first_air_date", "")

        return {
            "tmdb_id": data["id"],
            "media_type": "show",
            "title": data.get("name", ""),
            "original_title": data.get("original_name", ""),
            "year": int(first_air[:4]) if first_air else None,
            "genres": {g["id"]: g["name"] for g in data.get("genres", [])},
            "keywords": keywords,
            "cast_crew": {"cast": cast, "crew": crew_notable},
            "overview": data.get("overview", ""),
            "vote_average": data.get("vote_average"),
            "popularity": data.get("popularity"),
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "trailer_key": trailer_key,
            "runtime_minutes": data.get("episode_run_time", [None])[0] if data.get("episode_run_time") else None,
            "original_language": data.get("original_language"),
            "production_countries": [c["iso_3166_1"] for c in data.get("production_countries", [])],
            "similar_ids": similar_ids,
            "imdb_id": data.get("external_ids", {}).get("imdb_id"),
        }

    @staticmethod
    def _extract_trailer_key(videos: dict) -> Optional[str]:
        """Extract YouTube trailer key from TMDB videos response.

        Priority: Official Trailer > Trailer > Teaser > anything.
        Only YouTube results (for embedding).
        """
        results = videos.get("results", [])
        youtube = [v for v in results if v.get("site") == "YouTube"]

        # Priority ordering
        for type_name in ("Trailer", "Teaser", "Clip", "Featurette"):
            for v in youtube:
                if v.get("type") == type_name and v.get("official", True):
                    return v["key"]

        # Fallback: any YouTube video
        if youtube:
            return youtube[0]["key"]

        return None

    # ── Image URL helpers ────────────────────────────────────────

    @classmethod
    def poster_url(cls, path: Optional[str], size: str = "w500") -> Optional[str]:
        """Build full poster URL from TMDB path."""
        if not path:
            return None
        return f"{cls.IMAGE_BASE}/{size}{path}"

    @classmethod
    def backdrop_url(cls, path: Optional[str], size: str = "w1280") -> Optional[str]:
        """Build full backdrop URL from TMDB path."""
        if not path:
            return None
        return f"{cls.IMAGE_BASE}/{size}{path}"
