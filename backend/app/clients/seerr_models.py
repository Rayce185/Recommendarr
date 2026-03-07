"""Seerr data transfer objects and genre mappings."""

from dataclasses import dataclass, field
from typing import Optional


# ── Data Transfer Objects ────────────────────────────────────────

@dataclass
class SeerrMediaDetail:
    """Full metadata for a movie or TV show, sourced via Seerr's TMDB proxy."""
    tmdb_id: int
    media_type: str              # "movie" | "tv"
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    vote_average: float = 0.0
    vote_count: int = 0
    runtime: Optional[int] = None
    status: Optional[str] = None
    original_language: Optional[str] = None
    # External IDs
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    # Credits
    cast: list[dict] = field(default_factory=list)      # [{name, character, order}]
    directors: list[str] = field(default_factory=list)
    writers: list[str] = field(default_factory=list)
    # Trailers
    trailers: list[dict] = field(default_factory=list)   # [{name, key, site, type}]
    # Seerr-specific
    media_status: Optional[int] = None                    # 1=unknown, 2=pending, 3=processing, 4=partially_available, 5=available
    in_library: bool = False


@dataclass
class SeerrDiscoverResult:
    """Lightweight result from discover/trending endpoints."""
    tmdb_id: int
    media_type: str
    title: str
    year: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    vote_average: float = 0.0
    genre_ids: list[int] = field(default_factory=list)
    popularity: float = 0.0


@dataclass
class SeerrRequest:
    """A media request submitted through Seerr."""
    request_id: int
    tmdb_id: int
    media_type: str
    status: int                   # 1=pending, 2=approved, 3=declined
    requested_by: str
    created_at: Optional[str] = None


# ── Genre ID → Name mapping (TMDB standard) ─────────────────────

MOVIE_GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
}

TV_GENRE_MAP = {
    10759: "Action & Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    10762: "Kids", 9648: "Mystery", 10763: "News", 10764: "Reality",
    10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk",
    10768: "War & Politics", 37: "Western",
}


# ── Parsers ──────────────────────────────────────────────────────

def parse_detail(d: dict, media_type: str) -> SeerrMediaDetail:
    """Parse a full movie/TV detail response from Seerr."""
    # Genres
    genres = [g.get("name", "") for g in d.get("genres", []) if g.get("name")]

    # Keywords
    keywords = [k.get("name", "") for k in d.get("keywords", []) if k.get("name")]

    # Credits
    credits = d.get("credits", {})
    cast_raw = credits.get("cast", [])[:20]  # Top 20 cast
    cast = [
        {"name": c.get("name", ""), "character": c.get("character", ""), "order": c.get("order", 99)}
        for c in cast_raw
    ]
    crew_raw = credits.get("crew", [])
    directors = [c["name"] for c in crew_raw if c.get("job") == "Director"]
    writers = [c["name"] for c in crew_raw if c.get("department") == "Writing"][:5]

    # Trailers
    trailers = []
    rv = d.get("relatedVideos", [])
    video_list = rv.get("results", []) if isinstance(rv, dict) else rv if isinstance(rv, list) else []
    for v in video_list:
        if v.get("type") in ("Trailer", "Teaser"):
            trailers.append({
                "name": v.get("name", ""),
                "key": v.get("key", ""),
                "site": v.get("site", ""),
                "type": v.get("type", ""),
            })

    # Year extraction
    year = None
    date_str = d.get("releaseDate") or d.get("firstAirDate") or ""
    if date_str and len(date_str) >= 4:
        try:
            year = int(date_str[:4])
        except ValueError:
            pass

    # External IDs
    ext = d.get("externalIds", {})

    # Media status (Seerr availability tracking)
    media_info = d.get("mediaInfo")
    media_status = media_info.get("status") if media_info else None
    in_library = media_status in (4, 5) if media_status else False

    return SeerrMediaDetail(
        tmdb_id=d.get("id", 0),
        media_type=media_type,
        title=d.get("title") or d.get("name") or "",
        original_title=d.get("originalTitle") or d.get("originalName"),
        year=year,
        overview=d.get("overview"),
        poster_path=d.get("posterPath"),
        backdrop_path=d.get("backdropPath"),
        genres=genres,
        keywords=keywords,
        vote_average=d.get("voteAverage", 0.0),
        vote_count=d.get("voteCount", 0),
        runtime=d.get("runtime") or d.get("episodeRunTime", [None])[0] if isinstance(d.get("episodeRunTime"), list) and d.get("episodeRunTime") else d.get("runtime"),
        status=d.get("status"),
        original_language=d.get("originalLanguage"),
        imdb_id=ext.get("imdbId"),
        tvdb_id=ext.get("tvdbId"),
        cast=cast,
        directors=directors,
        writers=writers,
        trailers=trailers,
        media_status=media_status,
        in_library=in_library,
    )


def parse_discover_result(r: dict, media_type: str) -> SeerrDiscoverResult:
    """Parse a lightweight discover/trending/search result."""
    year = None
    date_str = r.get("releaseDate") or r.get("firstAirDate") or ""
    if date_str and len(date_str) >= 4:
        try:
            year = int(date_str[:4])
        except ValueError:
            pass

    return SeerrDiscoverResult(
        tmdb_id=r.get("id", 0),
        media_type=r.get("mediaType", media_type),
        title=r.get("title") or r.get("name") or "",
        year=year,
        overview=r.get("overview"),
        poster_path=r.get("posterPath"),
        vote_average=r.get("voteAverage", 0.0),
        genre_ids=r.get("genreIds", []),
        popularity=r.get("popularity", 0.0),
    )


def resolve_genre_ids(genre_ids: list[int], media_type: str = "movie") -> list[str]:
    """Convert TMDB genre IDs to names (for discover results)."""
    gmap = MOVIE_GENRE_MAP if media_type == "movie" else TV_GENRE_MAP
    return [gmap[gid] for gid in genre_ids if gid in gmap]
