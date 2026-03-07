"""Recommendation types and scoring constants.

Shared types used across the recommendation engine modules:
rec_scoring, rec_library, rec_modes, recommender.
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Scoring weights ──────────────────────────────────────────────

SCORE_WEIGHTS = {
    "genre_match": 0.28,
    "keyword_match": 0.18,
    "rating_quality": 0.14,
    "personnel_match": 0.10,
    "collaborative": 0.10,
    "popularity": 0.05,
    "mood_alignment": 0.10,
    "cultural_pulse": 0.05,
}


@dataclass
class Recommendation:
    tmdb_id: int
    media_type: str
    title: str
    year: Optional[int] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    overview: Optional[str] = None
    vote_average: float = 0.0
    runtime: Optional[int] = None
    original_language: Optional[str] = None
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    explanation: str = ""
    explanation_signals: list[str] = field(default_factory=list)
    mode: str = ""
    in_library: bool = False
    quality: Optional[str] = None
    source: Optional[str] = None
    directors: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    trailer_key: Optional[str] = None
    trailer_site: Optional[str] = None
    is_watched: bool = False
    user_feedback: Optional[str] = None


@dataclass
class RecommendationRequest:
    """Input parameters for generating recommendations."""
    username: str
    mode: str = "tonight"
    mood_text: Optional[str] = None
    mood_vector: Optional[object] = None
    mood_profile_id: Optional[int] = None
    domain: str = "all"
    genre_filter: Optional[str] = None
    limit: int = 20
    exclude_tmdb_ids: set[int] = field(default_factory=set)
    exclude_genres: set[str] = field(default_factory=set)
    include_genres: set[str] = field(default_factory=set)
    exclude_libraries: set[str] = field(default_factory=set)
    group_users: list[str] = field(default_factory=list)
    skip_explanations: bool = False
    _uid: Optional[str] = None
    _overrides: Optional[object] = None
    _dismissed_ids: set = field(default_factory=set)
