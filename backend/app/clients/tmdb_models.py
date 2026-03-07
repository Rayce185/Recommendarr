"""TMDB data transfer objects and constants.

Shared by tmdb.py, tmdb_cache.py, tmdb_discover.py, and any consumer
of TMDB API results.
"""

from dataclasses import dataclass, field
from typing import Optional


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


def parse_discover_result(r: dict, default_type: str = "movie") -> TMDBDiscoverResult:
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
