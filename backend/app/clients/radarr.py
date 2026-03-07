"""Radarr v3 API client — movie metadata and management."""

import httpx
import logging

from app.clients.servarr_models import ServarrMovie

logger = logging.getLogger(__name__)


class RadarrClient:
    """Radarr v3 API client."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.url}/api/v3/system/status", headers=self.headers)
                return resp.status_code == 200
        except Exception:
            return False

    async def get_all_movies(self) -> list[ServarrMovie]:
        """Fetch ALL movies from Radarr in one call."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{self.url}/api/v3/movie", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

        movies = []
        for m in data:
            tmdb_id = m.get("tmdbId")
            if not tmdb_id:
                continue
            ratings = m.get("ratings", {})
            vote_avg = ratings.get("tmdb", {}).get("value") or ratings.get("imdb", {}).get("value")
            quality = None
            if m.get("hasFile") and m.get("movieFile"):
                quality = m["movieFile"].get("quality", {}).get("quality", {}).get("name")
            poster = None
            for img in m.get("images", []):
                if img.get("coverType") == "poster":
                    poster = img.get("remoteUrl")
                    break
            lang = m.get("originalLanguage", {})
            lang_name = lang.get("name") if isinstance(lang, dict) else None

            movies.append(ServarrMovie(
                radarr_id=m["id"], tmdb_id=tmdb_id,
                imdb_id=m.get("imdbId"), title=m.get("title", ""),
                original_title=m.get("originalTitle"), year=m.get("year"),
                genres=m.get("genres", []), overview=m.get("overview"),
                runtime_minutes=m.get("runtime"), vote_average=vote_avg,
                popularity=m.get("popularity"), certification=m.get("certification"),
                studio=m.get("studio"), original_language=lang_name,
                poster_path=poster, has_file=m.get("hasFile", False),
                quality=quality, tags=m.get("tags", []),
            ))
        return movies

    async def get_tag_map(self) -> dict[int, str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.url}/api/v3/tag", headers=self.headers)
            resp.raise_for_status()
            return {t["id"]: t["label"] for t in resp.json()}

    async def get_quality_profiles(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.url}/api/v3/qualityprofile", headers=self.headers)
            resp.raise_for_status()
            return [{"id": p["id"], "name": p["name"]} for p in resp.json()]

    async def get_root_folders(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.url}/api/v3/rootfolder", headers=self.headers)
            resp.raise_for_status()
            return [{"id": f["id"], "path": f["path"], "freeSpace": f.get("freeSpace", 0)} for f in resp.json()]

    async def lookup_movie(self, tmdb_id: int) -> dict | None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3/movie/lookup/tmdb",
                params={"tmdbId": tmdb_id}, headers=self.headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def add_movie(self, tmdb_id: int, quality_profile_id: int,
                        root_folder: str, tags: list[int] | None = None,
                        monitored: bool = True, search_now: bool = True) -> dict:
        """Add a movie to Radarr by TMDB ID."""
        movie_data = await self.lookup_movie(tmdb_id)
        if not movie_data:
            raise ValueError(f"TMDB ID {tmdb_id} not found in Radarr lookup")
        movie_data["qualityProfileId"] = quality_profile_id
        movie_data["rootFolderPath"] = root_folder
        movie_data["monitored"] = monitored
        movie_data["tags"] = tags or []
        movie_data["addOptions"] = {"searchForMovie": search_now}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.url}/api/v3/movie", json=movie_data, headers=self.headers,
            )
            if resp.status_code == 400:
                err = resp.json()
                raise ValueError(err.get("message", str(err)))
            resp.raise_for_status()
            return resp.json()

    async def movie_exists(self, tmdb_id: int) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3/movie", params={"tmdbId": tmdb_id}, headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return len(data) > 0 if isinstance(data, list) else bool(data)

    async def get_calendar(self, days_ahead: int = 90) -> list[dict]:
        """Get upcoming movies from Radarr calendar (monitored items with future releases)."""
        from datetime import datetime, timedelta
        start = datetime.utcnow().strftime("%Y-%m-%d")
        end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{self.url}/api/v3/calendar",
                    headers=self.headers,
                    params={"start": start, "end": end, "unmonitored": "false"},
                )
                r.raise_for_status()
                items = r.json()
                return [
                    {
                        "title": m.get("title", "Unknown"),
                        "tmdb_id": m.get("tmdbId"),
                        "release_date": (
                            m.get("digitalRelease")
                            or m.get("physicalRelease")
                            or m.get("inCinemas")
                        ),
                        "media_type": "movie",
                        "poster": f"https://image.tmdb.org/t/p/w300{m['images'][0]['remoteUrl'].split('/t/p/')[1]}"
                            if m.get("images") and m["images"][0].get("remoteUrl") and "/t/p/" in m["images"][0].get("remoteUrl", "")
                            else None,
                        "source": "radarr",
                        "status": m.get("status", ""),
                        "monitored": True,
                        "has_file": m.get("hasFile", False),
                        "year": m.get("year"),
                        "overview": m.get("overview", ""),
                    }
                    for m in items
                ]
        except Exception as e:
            logger.warning("Radarr calendar failed: %s", e)
            return []
