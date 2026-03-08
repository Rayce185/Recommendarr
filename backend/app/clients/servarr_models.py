"""Servarr data models — shared between Radarr and Sonarr clients."""

from dataclasses import dataclass, field
from typing import Optional


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
    added_at: Optional[str] = None
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
    added_at: Optional[str] = None
    tags: list[int] = field(default_factory=list)
