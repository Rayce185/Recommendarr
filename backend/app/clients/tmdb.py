"""TMDB client — direct TMDB API access for discover/trending features.

Used for expanded trending sources (by country, streaming provider, new releases)
that Seerr's proxy doesn't support with full parameterization.
"""

import httpx
import json as _json
import logging

_logger = logging.getLogger(__name__)
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class TMDBDiscoverResult:
    """Lightweight result from TMDB discover/trending endpoints."""
    tmdb_id: int
    media_type: str
    title: str
    year: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: float = 0.0
    genre_ids: list[int] = field(default_factory=list)
    popularity: float = 0.0
    original_language: Optional[str] = None
    release_date: Optional[str] = None


@dataclass
class StreamingProvider:
    """A streaming provider available in a region."""
    provider_id: int
    provider_name: str
    logo_path: Optional[str] = None
    display_priority: int = 999


# Major streaming providers we highlight (subset of TMDB's full list)
FEATURED_PROVIDERS = {8, 119, 337, 350, 2, 3, 9, 384, 15, 531, 1899}
# 8=Netflix, 119=Amazon Prime, 337=Disney+, 350=Apple TV+, 2=Apple TV Store,
# 3=Google Play, 9=Amazon Video, 384=HBO Max, 15=Hulu, 531=Paramount+, 1899=Max

COUNTRY_OPTIONS = [
    {"code": "CH", "name": "Switzerland"},
    {"code": "DE", "name": "Germany"},
    {"code": "US", "name": "United States"},
    {"code": "GB", "name": "United Kingdom"},
    {"code": "FR", "name": "France"},
    {"code": "KR", "name": "South Korea"},
    {"code": "JP", "name": "Japan"},
    {"code": "IN", "name": "India"},
    {"code": "IT", "name": "Italy"},
    {"code": "ES", "name": "Spain"},
    {"code": "BR", "name": "Brazil"},
    {"code": "AU", "name": "Australia"},
]


class TMDBClient:
    """Direct TMDB API client for discover/trending features."""

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

    def _read_cache(self, tmdb_id: int, media_type: str) -> dict | None:
        """Read from SQLite tmdb_cache table."""
        try:
            from app.database import get_db
            from app.models.tables import TmdbCache
            from sqlalchemy import select, and_
            with get_db() as db:
                row = db.execute(
                    select(TmdbCache).where(
                        and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                    )
                ).scalar_one_or_none()
                if row and row.genres:
                    # Check cache_crew for schema v2 fields (trailers, networks)
                    cast_crew_raw = row.cast_crew if isinstance(row.cast_crew, dict) else _json.loads(row.cast_crew) if row.cast_crew else {}
                    if "trailers" not in cast_crew_raw:
                        return None  # Schema v1 entry — force re-fetch to get trailers, networks etc.
                    genres = row.genres if isinstance(row.genres, list) else _json.loads(row.genres) if row.genres else []
                    keywords = row.keywords if isinstance(row.keywords, list) else _json.loads(row.keywords) if row.keywords else []
                    cc = cast_crew_raw
                    return {
                        "tmdb_id": tmdb_id,
                        "media_type": media_type,
                        "title": row.title or "",
                        "original_title": row.original_title or "",
                        "year": row.year,
                        "overview": row.overview or "",
                        "poster_path": row.poster_path,
                        "backdrop_path": row.backdrop_path,
                        "vote_average": float(row.vote_average) if row.vote_average else 0,
                        "vote_count": cc.get("vote_count", 0),
                        "popularity": float(row.popularity) if row.popularity else 0,
                        "genres": genres,
                        "keywords": keywords,
                        "cast": cc.get("cast", []),
                        "crew": cc.get("crew", []),
                        "directors": cc.get("directors", []),
                        "runtime": row.runtime_minutes,
                        "original_language": row.original_language,
                        "imdb_id": cc.get("imdb_id"),
                        "tvdb_id": cc.get("tvdb_id"),
                        "tagline": cc.get("tagline", ""),
                        "production_companies": cc.get("production_companies", []),
                        "networks": cc.get("networks", []),
                        "trailers": cc.get("trailers", []),
                        "episode_runtime": cc.get("episode_runtime"),
                        "last_air_date": cc.get("last_air_date", ""),
                        "number_of_seasons": cc.get("number_of_seasons"),
                        "number_of_episodes": cc.get("number_of_episodes"),
                        "release_date": cc.get("release_date", ""),
                        "status": cc.get("status"),
                        "content_rating": "",
                    }
        except Exception:
            pass
        return None

    def _write_cache(self, tmdb_id: int, media_type: str, data: dict):
        """Write to SQLite tmdb_cache table (fire-and-forget)."""
        try:
            from app.database import get_db
            from app.models.tables import TmdbCache
            from sqlalchemy import select, and_

            cast_crew = {
                "cast": [c["name"] if isinstance(c, dict) else c for c in data.get("cast", [])[:10]],
                "crew": [{"name": c["name"], "job": c["job"]} for c in data.get("crew", []) if isinstance(c, dict)],
                "directors": data.get("directors", []) if isinstance(data.get("directors"), list) else [],
                "imdb_id": data.get("imdb_id"),
                "tvdb_id": data.get("tvdb_id"),
                "tagline": data.get("tagline", ""),
                "production_companies": data.get("production_companies", []),
                "networks": data.get("networks", []),
                "trailers": data.get("trailers", []),
                "episode_runtime": data.get("episode_runtime"),
                "last_air_date": data.get("last_air_date", ""),
                "number_of_seasons": data.get("number_of_seasons"),
                "number_of_episodes": data.get("number_of_episodes"),
                "release_date": data.get("release_date", ""),
                "status": data.get("status"),
                "vote_count": data.get("vote_count", 0),
            }

            with get_db() as db:
                existing = db.execute(
                    select(TmdbCache).where(
                        and_(TmdbCache.tmdb_id == tmdb_id, TmdbCache.media_type == media_type)
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.title = data.get("title", "")
                    existing.year = data.get("year")
                    existing.genres = _json.dumps(data.get("genres", []))
                    existing.keywords = _json.dumps(data.get("keywords", []))
                    existing.cast_crew = _json.dumps(cast_crew)
                    existing.overview = data.get("overview", "")
                    existing.vote_average = data.get("vote_average", 0)
                    existing.popularity = data.get("popularity", 0)
                    existing.poster_path = data.get("poster_path")
                    existing.backdrop_path = data.get("backdrop_path")
                    existing.runtime_minutes = data.get("runtime")
                    existing.original_language = data.get("original_language")
                else:
                    db.add(TmdbCache(
                        tmdb_id=tmdb_id, media_type=media_type,
                        title=data.get("title", ""),
                        original_title=data.get("original_title", ""),
                        year=data.get("year"),
                        genres=_json.dumps(data.get("genres", [])),
                        keywords=_json.dumps(data.get("keywords", [])),
                        cast_crew=_json.dumps(cast_crew),
                        overview=data.get("overview", ""),
                        vote_average=data.get("vote_average", 0),
                        popularity=data.get("popularity", 0),
                        poster_path=data.get("poster_path"),
                        backdrop_path=data.get("backdrop_path"),
                        runtime_minutes=data.get("runtime"),
                        original_language=data.get("original_language"),
                    ))
                db.commit()
        except Exception as e:
            _logger.debug(f"TMDB cache write failed for {tmdb_id}: {e}")

    async def close(self):
        """Close the persistent HTTP client."""
        await self._client.aclose()

    async def test_connection(self) -> bool:
        """Test TMDB API reachability."""
        try:
            d = await self._get("/configuration")
            return bool(d.get("images"))
        except Exception:
            return False

    # ── Trending ─────────────────────────────────────────────────

    async def get_trending(self, media_type: str = "all", window: str = "week",
                           page: int = 1) -> tuple[list[TMDBDiscoverResult], int]:
        """Global trending. media_type: all|movie|tv. window: day|week."""
        d = await self._get(f"/trending/{media_type}/{window}", {"page": page})
        results = [self._parse_result(r) for r in d.get("results", [])]
        return results, d.get("total_pages", 1)

    # ── Discover by Country ──────────────────────────────────────

    async def discover_by_country(self, region: str, media_type: str = "movie",
                                   page: int = 1) -> tuple[list[TMDBDiscoverResult], int]:
        """Popular content in a specific country/region."""
        if media_type == "movie":
            d = await self._get("/discover/movie", {
                "region": region,
                "sort_by": "popularity.desc",
                "page": page,
                "vote_count.gte": 10,
            })
        else:
            d = await self._get("/discover/tv", {
                "watch_region": region,
                "sort_by": "popularity.desc",
                "page": page,
                "vote_count.gte": 10,
            })
        results = [self._parse_result(r, media_type) for r in d.get("results", [])]
        return results, d.get("total_pages", 1)

    # ── Discover by Streaming Provider ───────────────────────────

    async def discover_by_provider(self, provider_id: int, region: str = "CH",
                                    media_type: str = "movie",
                                    page: int = 1) -> tuple[list[TMDBDiscoverResult], int]:
        """Popular content on a specific streaming provider in a region."""
        endpoint = "/discover/movie" if media_type == "movie" else "/discover/tv"
        d = await self._get(endpoint, {
            "watch_region": region,
            "with_watch_providers": str(provider_id),
            "sort_by": "popularity.desc",
            "page": page,
        })
        results = [self._parse_result(r, media_type) for r in d.get("results", [])]
        return results, d.get("total_pages", 1)

    async def get_providers(self, region: str = "CH",
                            media_type: str = "movie") -> list[StreamingProvider]:
        """Get available streaming providers for a region."""
        endpoint = f"/watch/providers/{'movie' if media_type == 'movie' else 'tv'}"
        d = await self._get(endpoint, {"watch_region": region})
        providers = []
        for p in d.get("results", []):
            providers.append(StreamingProvider(
                provider_id=p["provider_id"],
                provider_name=p["provider_name"],
                logo_path=p.get("logo_path"),
                display_priority=p.get("display_priority", 999),
            ))
        # Sort: featured first (by display_priority), then non-featured
        featured = [p for p in providers if p.provider_id in FEATURED_PROVIDERS]
        featured.sort(key=lambda p: p.display_priority)
        return featured

    # ── New Releases ─────────────────────────────────────────────

    async def discover_new_releases(self, days: int = 90, media_type: str = "movie",
                                     page: int = 1) -> tuple[list[TMDBDiscoverResult], int]:
        """Recently released content sorted by popularity."""
        now = datetime.utcnow()
        date_from = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")

        if media_type == "movie":
            d = await self._get("/discover/movie", {
                "sort_by": "popularity.desc",
                "primary_release_date.gte": date_from,
                "primary_release_date.lte": date_to,
                "page": page,
                "vote_count.gte": 5,
            })
        else:
            d = await self._get("/discover/tv", {
                "sort_by": "popularity.desc",
                "first_air_date.gte": date_from,
                "first_air_date.lte": date_to,
                "page": page,
                "vote_count.gte": 5,
            })
        results = [self._parse_result(r, media_type) for r in d.get("results", [])]
        return results, d.get("total_pages", 1)

    # ── Parser ───────────────────────────────────────────────────

    def _parse_result(self, r: dict, default_type: str = "movie") -> TMDBDiscoverResult:
        """Parse a TMDB result dict into our DTO."""
        media_type = r.get("media_type", default_type)
        year = None
        date_str = r.get("release_date") or r.get("first_air_date") or ""
        if date_str and len(date_str) >= 4:
            try:
                year = int(date_str[:4])
            except ValueError:
                pass
        return TMDBDiscoverResult(
            tmdb_id=r.get("id", 0),
            media_type=media_type,
            title=r.get("title") or r.get("name") or "",
            year=year,
            overview=r.get("overview"),
            poster_path=r.get("poster_path"),
            backdrop_path=r.get("backdrop_path"),
            vote_average=r.get("vote_average", 0.0),
            genre_ids=r.get("genre_ids", []),
            popularity=r.get("popularity", 0.0),
            original_language=r.get("original_language"),
            release_date=date_str,
        )


    # ── Detail ───────────────────────────────────────────────────

    async def get_detail(self, tmdb_id: int, media_type: str = "movie") -> dict:
        """Full detail for a movie or TV show — SQLite-cached, TMDB API on miss."""
        # Check SQLite cache first
        cached = self._read_cache(tmdb_id, media_type)
        if cached is not None:
            return cached

        endpoint = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        append = "keywords,credits,external_ids,videos"
        if media_type == "movie":
            append += ",release_dates"
        else:
            append += ",content_ratings"
        d = await self._get(endpoint, {"append_to_response": append})
        genres = [g["name"] for g in d.get("genres", [])]

        # Keywords
        kw_data = d.get("keywords", {})
        if media_type == "movie":
            keywords = [k["name"] for k in kw_data.get("keywords", [])]
        else:
            keywords = [k["name"] for k in kw_data.get("results", [])]

        # Cast/crew (top 10 cast, key crew)
        credits = d.get("credits", {})
        cast = [{"name": c["name"], "character": c.get("character", ""), "order": c.get("order", 99)}
                for c in credits.get("cast", [])[:10]]
        crew = [{"name": c["name"], "job": c["job"]}
                for c in credits.get("crew", [])
                if c.get("job") in ("Director", "Creator", "Writer", "Executive Producer")]

        date_str = d.get("release_date") or d.get("first_air_date") or ""
        year = int(date_str[:4]) if len(date_str) >= 4 else None

        external = d.get("external_ids", {})

        # Videos — extract YouTube trailers
        videos = d.get("videos", {}).get("results", [])
        trailers = [
            {"key": v["key"], "name": v.get("name", "Trailer"), "site": v["site"], "type": v.get("type", "")}
            for v in videos
            if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")
        ][:5]  # Max 5 trailers

        # Content certification
        certification = ""
        if media_type == "movie":
            for country_release in d.get("release_dates", {}).get("results", []):
                if country_release.get("iso_3166_1") in ("US", "CH", "DE"):
                    for rd in country_release.get("release_dates", []):
                        if rd.get("certification"):
                            certification = rd["certification"]
                            break
                if certification:
                    break
        else:
            for cr in d.get("content_ratings", {}).get("results", []):
                if cr.get("iso_3166_1") in ("US", "CH", "DE"):
                    certification = cr.get("rating", "")
                    break

        # Networks (TV only)
        networks = [n["name"] for n in d.get("networks", [])]

        # Episode runtime (TV: episode_run_time is a list, take first)
        ep_runtime = d.get("episode_run_time", [])
        episode_runtime = ep_runtime[0] if ep_runtime else None

        # Last air date for TV
        last_air_date = d.get("last_air_date", "")

        result = {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": d.get("title") or d.get("name") or "",
            "original_title": d.get("original_title") or d.get("original_name") or "",
            "year": year,
            "overview": d.get("overview", ""),
            "poster_path": d.get("poster_path"),
            "backdrop_path": d.get("backdrop_path"),
            "vote_average": d.get("vote_average", 0),
            "vote_count": d.get("vote_count", 0),
            "popularity": d.get("popularity", 0),
            "genres": genres,
            "keywords": keywords,
            "cast": cast,
            "crew": crew,
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
            "trailers": trailers,
            "networks": networks,
            "episode_runtime": episode_runtime,
            "last_air_date": last_air_date,
        }
        self._write_cache(tmdb_id, media_type, result)
        return result

    # ── Watch Providers ───────────────────────────────────────────

    async def get_watch_providers(self, tmdb_id: int, media_type: str = "movie", region: str = "CH") -> dict:
        """Get streaming/rent/buy providers for a title in a given region."""
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

    # ── Keywords ─────────────────────────────────────────────────

    async def get_keywords(self, tmdb_id: int, media_type: str = "movie") -> list[str]:
        """Get keyword list for a movie or TV show."""
        if media_type == "movie":
            d = await self._get(f"/movie/{tmdb_id}/keywords")
            return [k["name"] for k in d.get("keywords", [])]
        else:
            d = await self._get(f"/tv/{tmdb_id}/keywords")
            return [k["name"] for k in d.get("results", [])]

    # ── Similar / Recommendations ────────────────────────────────

    async def get_similar(self, tmdb_id: int, media_type: str = "movie",
                          page: int = 1) -> list[TMDBDiscoverResult]:
        """Get similar titles from TMDB."""
        endpoint = f"/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/similar"
        d = await self._get(endpoint, {"page": page})
        return [self._parse_result(r, media_type) for r in d.get("results", [])]

    async def get_recommendations_for(self, tmdb_id: int, media_type: str = "movie",
                                       page: int = 1) -> list[TMDBDiscoverResult]:
        """Get TMDB recommendations for a title."""
        endpoint = f"/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/recommendations"
        d = await self._get(endpoint, {"page": page})
        return [self._parse_result(r, media_type) for r in d.get("results", [])]

    # ── Search ───────────────────────────────────────────────────

    async def search(self, query: str, page: int = 1) -> list[TMDBDiscoverResult]:
        """Multi-search across movies, TV, people."""
        d = await self._get("/search/multi", {"query": query, "page": page})
        results = []
        for r in d.get("results", []):
            if r.get("media_type") in ("movie", "tv"):
                results.append(self._parse_result(r))
        return results

    # ── Genre Lists ──────────────────────────────────────────────

    async def get_movie_genres(self) -> list[dict]:
        """Return [{id, name}, ...] for movie genres."""
        d = await self._get("/genre/movie/list")
        return d.get("genres", [])

    async def get_tv_genres(self) -> list[dict]:
        """Return [{id, name}, ...] for TV genres."""
        d = await self._get("/genre/tv/list")
        return d.get("genres", [])

    # ── Discover by Genre ────────────────────────────────────────

    async def discover_by_genre(self, genre_id: int, media_type: str = "movie",
                                 page: int = 1) -> list[TMDBDiscoverResult]:
        """Discover popular titles by genre."""
        endpoint = "/discover/movie" if media_type == "movie" else "/discover/tv"
        d = await self._get(endpoint, {
            "with_genres": str(genre_id),
            "sort_by": "popularity.desc",
            "page": page,
            "vote_count.gte": 10,
        })
        return [self._parse_result(r, media_type) for r in d.get("results", [])]

    @staticmethod
    def get_country_options() -> list[dict]:
        """Return the list of available country options."""
        return COUNTRY_OPTIONS

    # ── Collections ──────────────────────────────────────────────

    async def get_movie_collection_id(self, tmdb_id: int) -> dict | None:
        """Get collection info for a movie (if it belongs to one).
        Returns {"id": int, "name": str} or None."""
        try:
            d = await self._get(f"/movie/{tmdb_id}", {})
            coll = d.get("belongs_to_collection")
            if coll:
                return {"id": coll["id"], "name": coll["name"], "poster_path": coll.get("poster_path")}
            return None
        except Exception:
            return None

    async def get_collection(self, collection_id: int) -> dict | None:
        """Get full collection details with all parts."""
        try:
            d = await self._get(f"/collection/{collection_id}", {})
            parts = []
            for p in d.get("parts", []):
                date_str = p.get("release_date") or ""
                year = int(date_str[:4]) if len(date_str) >= 4 else None
                parts.append({
                    "tmdb_id": p["id"],
                    "title": p.get("title", ""),
                    "year": year,
                    "poster_path": p.get("poster_path"),
                    "vote_average": p.get("vote_average", 0),
                    "overview": p.get("overview", ""),
                    "release_date": date_str,
                })
            parts.sort(key=lambda x: x.get("release_date") or "9999")
            return {
                "collection_id": collection_id,
                "name": d.get("name", ""),
                "overview": d.get("overview", ""),
                "poster_path": d.get("poster_path"),
                "backdrop_path": d.get("backdrop_path"),
                "parts": parts,
            }
        except Exception:
            return None
