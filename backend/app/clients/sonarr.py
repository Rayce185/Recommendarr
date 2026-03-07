"""Sonarr v3 API client — series metadata and management."""

import httpx
import logging

from app.clients.servarr_models import ServarrSeries

logger = logging.getLogger(__name__)


class SonarrClient:
    """Sonarr v3 API client."""

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

    async def get_tag_map(self) -> dict[int, str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.url}/api/v3/tag", headers=self.headers)
            resp.raise_for_status()
            return {t["id"]: t["label"] for t in resp.json()}

    async def get_all_series(self) -> list[ServarrSeries]:
        """Fetch ALL series from Sonarr in one call."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{self.url}/api/v3/series", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

        series = []
        for s in data:
            tvdb_id = s.get("tvdbId")
            tmdb_id = s.get("tmdbId")
            poster = None
            for img in s.get("images", []):
                if img.get("coverType") == "poster":
                    poster = img.get("remoteUrl")
                    break
            ratings = s.get("ratings", {})
            stats = s.get("statistics", {})

            series.append(ServarrSeries(
                sonarr_id=s["id"], tvdb_id=tvdb_id, tmdb_id=tmdb_id,
                imdb_id=s.get("imdbId"), title=s.get("title", ""),
                year=s.get("year"), genres=s.get("genres", []),
                overview=s.get("overview"), runtime_minutes=s.get("runtime"),
                vote_average=ratings.get("value"),
                certification=s.get("certification"), network=s.get("network"),
                original_language=s.get("originalLanguage", {}).get("name")
                    if isinstance(s.get("originalLanguage"), dict) else None,
                poster_path=poster, status=s.get("status"),
                season_count=stats.get("seasonCount", 0),
                episode_count=stats.get("totalEpisodeCount", 0),
                tags=s.get("tags", []),
            ))
        return series

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

    async def lookup_series(self, tvdb_id: int | None = None, tmdb_id: int | None = None,
                            term: str | None = None) -> dict | None:
        """Lookup a series by TVDB ID, TMDB ID, or search term."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            if tvdb_id:
                params = {"term": f"tvdb:{tvdb_id}"}
            elif tmdb_id:
                params = {"term": f"tmdb:{tmdb_id}"}
            elif term:
                params = {"term": term}
            else:
                return None

            resp = await client.get(
                f"{self.url}/api/v3/series/lookup", params=params, headers=self.headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return data[0] if isinstance(data, list) and data else (data if not isinstance(data, list) else None)

    async def add_series(self, tvdb_id: int | None = None, tmdb_id: int | None = None,
                         quality_profile_id: int = 1, root_folder: str = "/media/Series",
                         tags: list[int] | None = None, monitored: bool = True,
                         search_now: bool = True, series_type: str = "standard",
                         season_folder: bool = True) -> dict:
        """Add a series to Sonarr. series_type: standard|anime|daily."""
        series_data = await self.lookup_series(tvdb_id=tvdb_id, tmdb_id=tmdb_id)
        if not series_data:
            raise ValueError(f"Series not found (tvdb={tvdb_id}, tmdb={tmdb_id})")
        series_data["qualityProfileId"] = quality_profile_id
        series_data["rootFolderPath"] = root_folder
        series_data["monitored"] = monitored
        series_data["tags"] = tags or []
        series_data["seriesType"] = series_type
        series_data["seasonFolder"] = season_folder
        series_data["addOptions"] = {
            "searchForMissingEpisodes": search_now,
            "searchForCutoffUnmetEpisodes": False,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.url}/api/v3/series", json=series_data, headers=self.headers,
            )
            if resp.status_code == 400:
                err = resp.json()
                raise ValueError(
                    err[0].get("errorMessage", str(err)) if isinstance(err, list)
                    else err.get("message", str(err))
                )
            resp.raise_for_status()
            return resp.json()

    async def series_exists(self, tvdb_id: int | None = None, tmdb_id: int | None = None) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.url}/api/v3/series", headers=self.headers)
            resp.raise_for_status()
            for s in resp.json():
                if tvdb_id and s.get("tvdbId") == tvdb_id:
                    return True
                if tmdb_id and s.get("tmdbId") == tmdb_id:
                    return True
            return False
