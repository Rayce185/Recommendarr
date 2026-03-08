"""TMDB client — direct TMDB API access for detail, search, and discovery.

Delegates discovery/trending to tmdb_discover module, cache to tmdb_cache,
and uses shared DTOs from tmdb_models. This file owns the HTTP client,
detail fetching, search, and collection endpoints.
"""

import httpx
import logging

from app.clients.tmdb_models import (
    TMDBDiscoverResult,
    StreamingProvider,
    FEATURED_PROVIDERS,
    COUNTRY_OPTIONS,
    parse_discover_result,
)
from app.clients.tmdb_cache import read_cache, write_cache
from app.clients import tmdb_discover

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "TMDBClient",
    "TMDBDiscoverResult",
    "StreamingProvider",
    "FEATURED_PROVIDERS",
    "COUNTRY_OPTIONS",
]


class TMDBClient:
    """Direct TMDB API client for detail, search, and discovery."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=20),
            http2=False,
        )

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """GET request to TMDB API (persistent connection pool)."""
        p = {"api_key": self.api_key}
        if params:
            p.update(params)
        resp = await self._client.get(f"{self.base_url}{path}", params=p)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()

    async def test_connection(self) -> bool:
        try:
            d = await self._get("/configuration")
            return bool(d.get("images"))
        except Exception:
            return False

    # ── Detail (cached) ──────────────────────────────────────────

    async def get_detail(self, tmdb_id: int, media_type: str = "movie") -> dict:
        """Full detail for a movie or TV show — SQLite-cached, TMDB API on miss."""
        cached = read_cache(tmdb_id, media_type)
        if cached is not None:
            return cached

        endpoint = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        append = "keywords,credits,external_ids,videos"
        append += ",release_dates" if media_type == "movie" else ",content_ratings"
        d = await self._get(endpoint, {"append_to_response": append})

        result = self._build_detail_result(d, tmdb_id, media_type)
        write_cache(tmdb_id, media_type, result)
        return result

    def _build_detail_result(self, d: dict, tmdb_id: int, media_type: str) -> dict:
        """Transform raw TMDB API response into our detail dict."""
        genres = [g["name"] for g in d.get("genres", [])]

        kw_data = d.get("keywords", {})
        keywords = [k["name"] for k in kw_data.get(
            "keywords" if media_type == "movie" else "results", []
        )]

        credits = d.get("credits", {})
        cast = [
            {"name": c["name"], "character": c.get("character", ""), "order": c.get("order", 99)}
            for c in credits.get("cast", [])[:10]
        ]
        crew = [
            {"name": c["name"], "job": c["job"]}
            for c in credits.get("crew", [])
            if c.get("job") in ("Director", "Creator", "Writer", "Executive Producer")
        ]

        date_str = d.get("release_date") or d.get("first_air_date") or ""
        year = int(date_str[:4]) if len(date_str) >= 4 else None
        external = d.get("external_ids", {})

        videos = d.get("videos", {}).get("results", [])
        trailers = [
            {"key": v["key"], "name": v.get("name", "Trailer"), "site": v["site"], "type": v.get("type", "")}
            for v in videos
            if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")
        ][:5]

        certification = self._extract_certification(d, media_type)
        networks = [n["name"] for n in d.get("networks", [])]
        ep_runtime = d.get("episode_run_time", [])

        return {
            "tmdb_id": tmdb_id, "media_type": media_type,
            "title": d.get("title") or d.get("name") or "",
            "original_title": d.get("original_title") or d.get("original_name") or "",
            "year": year,
            "overview": d.get("overview", ""),
            "poster_path": d.get("poster_path"),
            "backdrop_path": d.get("backdrop_path"),
            "vote_average": d.get("vote_average", 0),
            "vote_count": d.get("vote_count", 0),
            "popularity": d.get("popularity", 0),
            "genres": genres, "keywords": keywords,
            "cast": cast, "crew": crew,
            "runtime": d.get("runtime"),
            "status": d.get("status"),
            "tagline": d.get("tagline", ""),
            "original_language": d.get("original_language"),
            "production_companies": [c["name"] for c in d.get("production_companies", [])],
            "content_rating": certification or d.get("content_rating", ""),
            "imdb_id": external.get("imdb_id"),
            "tvdb_id": external.get("tvdb_id"),
            "release_date": date_str,
            "number_of_seasons": d.get("number_of_seasons"),
            "number_of_episodes": d.get("number_of_episodes"),
            "trailers": trailers, "networks": networks,
            "episode_runtime": ep_runtime[0] if ep_runtime else None,
            "last_air_date": d.get("last_air_date", ""),
        }

    @staticmethod
    def _extract_certification(d: dict, media_type: str) -> str:
        """Extract content rating from release_dates or content_ratings."""
        if media_type == "movie":
            for cr in d.get("release_dates", {}).get("results", []):
                if cr.get("iso_3166_1") in ("US", "CH", "DE"):
                    for rd in cr.get("release_dates", []):
                        if rd.get("certification"):
                            return rd["certification"]
        else:
            for cr in d.get("content_ratings", {}).get("results", []):
                if cr.get("iso_3166_1") in ("US", "CH", "DE"):
                    return cr.get("rating", "")
        return ""

    # ── Search / Keywords / Providers / Similar ──────────────────

    async def search(self, query: str, page: int = 1) -> list[TMDBDiscoverResult]:
        d = await self._get("/search/multi", {"query": query, "page": page})
        return [
            parse_discover_result(r)
            for r in d.get("results", [])
            if r.get("media_type") in ("movie", "tv")
        ]

    async def get_keywords(self, tmdb_id: int, media_type: str = "movie") -> list[str]:
        if media_type == "movie":
            d = await self._get(f"/movie/{tmdb_id}/keywords")
            return [k["name"] for k in d.get("keywords", [])]
        else:
            d = await self._get(f"/tv/{tmdb_id}/keywords")
            return [k["name"] for k in d.get("results", [])]

    async def get_watch_providers(self, tmdb_id: int, media_type: str = "movie", region: str = "CH") -> dict:
        endpoint = f"/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/watch/providers"
        try:
            d = await self._get(endpoint)
            results = d.get("results", {}).get(region, {})
            providers = {}
            for category in ("flatrate", "rent", "buy", "free"):
                items = results.get(category, [])
                if items:
                    providers[category] = [
                        {"provider_name": p["provider_name"], "logo_path": p.get("logo_path")}
                        for p in items[:6]
                    ]
            return {"providers": providers, "link": results.get("link", "")}
        except Exception:
            return {"providers": {}, "link": ""}

    async def get_similar(self, tmdb_id: int, media_type: str = "movie", page: int = 1) -> list[TMDBDiscoverResult]:
        endpoint = f"/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/similar"
        d = await self._get(endpoint, {"page": page})
        return [parse_discover_result(r, media_type) for r in d.get("results", [])]

    async def get_recommendations_for(self, tmdb_id: int, media_type: str = "movie", page: int = 1) -> list[TMDBDiscoverResult]:
        endpoint = f"/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/recommendations"
        d = await self._get(endpoint, {"page": page})
        return [parse_discover_result(r, media_type) for r in d.get("results", [])]

    # ── Genre Lists ──────────────────────────────────────────────

    async def get_movie_genres(self) -> list[dict]:
        return (await self._get("/genre/movie/list")).get("genres", [])

    async def get_tv_genres(self) -> list[dict]:
        return (await self._get("/genre/tv/list")).get("genres", [])

    # ── Collections ──────────────────────────────────────────────

    async def get_movie_collection_id(self, tmdb_id: int) -> dict | None:
        try:
            d = await self._get(f"/movie/{tmdb_id}", {})
            coll = d.get("belongs_to_collection")
            if coll:
                return {"id": coll["id"], "name": coll["name"], "poster_path": coll.get("poster_path")}
        except Exception:
            pass
        return None

    async def get_collection(self, collection_id: int) -> dict | None:
        try:
            d = await self._get(f"/collection/{collection_id}", {})
            parts = []
            for p in d.get("parts", []):
                date_str = p.get("release_date") or ""
                year = int(date_str[:4]) if len(date_str) >= 4 else None
                parts.append({
                    "tmdb_id": p["id"], "title": p.get("title", ""),
                    "year": year, "poster_path": p.get("poster_path"),
                    "vote_average": p.get("vote_average", 0),
                    "overview": p.get("overview", ""), "release_date": date_str,
                })
            parts.sort(key=lambda x: x.get("release_date") or "9999")
            return {
                "collection_id": collection_id, "name": d.get("name", ""),
                "overview": d.get("overview", ""),
                "poster_path": d.get("poster_path"),
                "backdrop_path": d.get("backdrop_path"), "parts": parts,
            }
        except Exception:
            return None

    # ── Discovery delegation (backward compat) ───────────────────

    async def get_trending(self, media_type="all", window="week", page=1):
        return await tmdb_discover.get_trending(self._get, media_type, window, page)

    async def discover_by_country(self, region, media_type="movie", page=1, extra_params=None):
        return await tmdb_discover.discover_by_country(self._get, region, media_type, page, extra_params)

    async def discover_by_provider(self, provider_id, region="CH", media_type="movie", page=1, extra_params=None):
        return await tmdb_discover.discover_by_provider(self._get, provider_id, region, media_type, page, extra_params)

    async def get_providers(self, region="CH", media_type="movie"):
        return await tmdb_discover.get_providers(self._get, region, media_type)

    async def discover_new_releases(self, days=90, media_type="movie", page=1, extra_params=None):
        return await tmdb_discover.discover_new_releases(self._get, days, media_type, page, extra_params)

    async def discover_popular(self, media_type="movie", page=1, extra_params=None):
        return await tmdb_discover.discover_popular(self._get, media_type, page, extra_params)

    async def discover_by_genre(self, genre_id, media_type="movie", page=1):
        return await tmdb_discover.discover_by_genre(self._get, genre_id, media_type, page)

    @staticmethod
    def get_country_options():
        return COUNTRY_OPTIONS

    async def discover_upcoming(self, media_type="movie", days_ahead=90, page=1):
        return await tmdb_discover.discover_upcoming(self._get, media_type, days_ahead, page)

    async def discover_recent(self, media_type="movie", days_back=30):
        return await tmdb_discover.discover_recent(self._get, media_type, days_back)
