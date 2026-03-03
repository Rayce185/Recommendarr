"""Servarr API clients — Radarr + Sonarr metadata extraction.

Primary metadata source for Recommendarr. Pulls movie/show data
from local Radarr/Sonarr instances instead of hitting TMDB API.
"""

import httpx
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ServarrMovie:
    """Normalized movie record from Radarr."""
    radarr_id: int
    tmdb_id: int
    imdb_id: Optional[str]
    title: str
    original_title: Optional[str]
    year: Optional[int]
    genres: list[str]
    overview: Optional[str]
    runtime_minutes: Optional[int]
    vote_average: Optional[float]
    popularity: Optional[float]
    certification: Optional[str]
    studio: Optional[str]
    original_language: Optional[str]
    poster_path: Optional[str]
    has_file: bool
    quality: Optional[str]
    tags: list[int] = field(default_factory=list)


@dataclass
class ServarrSeries:
    """Normalized series record from Sonarr."""
    sonarr_id: int
    tvdb_id: Optional[int]
    tmdb_id: Optional[int]
    imdb_id: Optional[str]
    title: str
    year: Optional[int]
    genres: list[str]
    overview: Optional[str]
    runtime_minutes: Optional[int]
    vote_average: Optional[float]
    certification: Optional[str]
    network: Optional[str]
    original_language: Optional[str]
    poster_path: Optional[str]
    status: Optional[str]
    season_count: int
    episode_count: int
    tags: list[int] = field(default_factory=list)


class RadarrClient:
    """Radarr v3 API client."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/api/v3/system/status", headers=self.headers
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def get_all_movies(self) -> list[ServarrMovie]:
        """Fetch ALL movies from Radarr in one call."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3/movie", headers=self.headers
            )
            resp.raise_for_status()
            data = resp.json()

        movies = []
        for m in data:
            tmdb_id = m.get("tmdbId")
            if not tmdb_id:
                continue

            # Extract rating (prefer TMDB, fallback IMDB)
            ratings = m.get("ratings", {})
            tmdb_rating = ratings.get("tmdb", {}).get("value")
            imdb_rating = ratings.get("imdb", {}).get("value")
            vote_avg = tmdb_rating or imdb_rating

            # Extract quality from file
            quality = None
            if m.get("hasFile") and m.get("movieFile"):
                quality = (
                    m["movieFile"]
                    .get("quality", {})
                    .get("quality", {})
                    .get("name")
                )

            # Extract poster
            poster = None
            for img in m.get("images", []):
                if img.get("coverType") == "poster":
                    poster = img.get("remoteUrl")
                    break

            # Language
            lang = m.get("originalLanguage", {})
            lang_name = lang.get("name") if isinstance(lang, dict) else None

            movies.append(ServarrMovie(
                radarr_id=m["id"],
                tmdb_id=tmdb_id,
                imdb_id=m.get("imdbId"),
                title=m.get("title", ""),
                original_title=m.get("originalTitle"),
                year=m.get("year"),
                genres=m.get("genres", []),
                overview=m.get("overview"),
                runtime_minutes=m.get("runtime"),
                vote_average=vote_avg,
                popularity=m.get("popularity"),
                certification=m.get("certification"),
                studio=m.get("studio"),
                original_language=lang_name,
                poster_path=poster,
                has_file=m.get("hasFile", False),
                quality=quality,
                tags=m.get("tags", []),
            ))

        return movies

    async def get_tag_map(self) -> dict[int, str]:
        """Get tag ID to name mapping."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3/tag", headers=self.headers
            )
            resp.raise_for_status()
            return {t["id"]: t["label"] for t in resp.json()}


class SonarrClient:
    """Sonarr v3 API client."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/api/v3/system/status", headers=self.headers
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def get_all_series(self) -> list[ServarrSeries]:
        """Fetch ALL series from Sonarr in one call."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3/series", headers=self.headers
            )
            resp.raise_for_status()
            data = resp.json()

        series = []
        for s in data:
            # Sonarr uses TVDB primarily, but may have TMDB
            tvdb_id = s.get("tvdbId")
            # TMDB ID might be in the ratings or alternate IDs
            tmdb_id = s.get("tmdbId")  # Some Sonarr versions have this

            # Poster
            poster = None
            for img in s.get("images", []):
                if img.get("coverType") == "poster":
                    poster = img.get("remoteUrl")
                    break

            # Ratings
            ratings = s.get("ratings", {})
            vote_avg = ratings.get("value")

            # Episode stats
            stats = s.get("statistics", {})

            series.append(ServarrSeries(
                sonarr_id=s["id"],
                tvdb_id=tvdb_id,
                tmdb_id=tmdb_id,
                imdb_id=s.get("imdbId"),
                title=s.get("title", ""),
                year=s.get("year"),
                genres=s.get("genres", []),
                overview=s.get("overview"),
                runtime_minutes=s.get("runtime"),
                vote_average=vote_avg,
                certification=s.get("certification"),
                network=s.get("network"),
                original_language=s.get("originalLanguage", {}).get("name")
                    if isinstance(s.get("originalLanguage"), dict) else None,
                poster_path=poster,
                status=s.get("status"),
                season_count=stats.get("seasonCount", 0),
                episode_count=stats.get("totalEpisodeCount", 0),
                tags=s.get("tags", []),
            ))

        return series
