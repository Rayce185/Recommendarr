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
    # Europe
    {"code": "CH", "name": "Switzerland"},
    {"code": "DE", "name": "Germany"},
    {"code": "GB", "name": "United Kingdom"},
    {"code": "FR", "name": "France"},
    {"code": "IT", "name": "Italy"},
    {"code": "ES", "name": "Spain"},
    {"code": "NL", "name": "Netherlands"},
    {"code": "BE", "name": "Belgium"},
    {"code": "AT", "name": "Austria"},
    {"code": "PT", "name": "Portugal"},
    {"code": "SE", "name": "Sweden"},
    {"code": "NO", "name": "Norway"},
    {"code": "DK", "name": "Denmark"},
    {"code": "FI", "name": "Finland"},
    {"code": "PL", "name": "Poland"},
    {"code": "CZ", "name": "Czech Republic"},
    {"code": "IE", "name": "Ireland"},
    {"code": "GR", "name": "Greece"},
    {"code": "RO", "name": "Romania"},
    {"code": "HU", "name": "Hungary"},
    {"code": "TR", "name": "Turkey"},
    {"code": "RU", "name": "Russia"},
    {"code": "UA", "name": "Ukraine"},
    # Americas
    {"code": "US", "name": "United States"},
    {"code": "CA", "name": "Canada"},
    {"code": "MX", "name": "Mexico"},
    {"code": "BR", "name": "Brazil"},
    {"code": "AR", "name": "Argentina"},
    {"code": "CO", "name": "Colombia"},
    {"code": "CL", "name": "Chile"},
    # Asia & Pacific
    {"code": "JP", "name": "Japan"},
    {"code": "KR", "name": "South Korea"},
    {"code": "CN", "name": "China"},
    {"code": "IN", "name": "India"},
    {"code": "TH", "name": "Thailand"},
    {"code": "PH", "name": "Philippines"},
    {"code": "ID", "name": "Indonesia"},
    {"code": "MY", "name": "Malaysia"},
    {"code": "SG", "name": "Singapore"},
    {"code": "TW", "name": "Taiwan"},
    {"code": "HK", "name": "Hong Kong"},
    {"code": "AU", "name": "Australia"},
    {"code": "NZ", "name": "New Zealand"},
    # Middle East & Africa
    {"code": "IL", "name": "Israel"},
    {"code": "AE", "name": "United Arab Emirates"},
    {"code": "SA", "name": "Saudi Arabia"},
    {"code": "EG", "name": "Egypt"},
    {"code": "ZA", "name": "South Africa"},
    {"code": "NG", "name": "Nigeria"},
    {"code": "KE", "name": "Kenya"},
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
