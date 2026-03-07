"""Taste profile data structures and constants.

Shared by taste_profiler, taste_enrichment, taste_collaborative,
and any consumer of taste profile data.
"""

import math
from datetime import datetime, timezone
from dataclasses import dataclass, field


# ── Signal weights (from spec §3.1) ─────────────────────────────

SIGNAL_WEIGHTS = {
    "completion_full": 5.0,       # ≥85% watched
    "completion_good": 2.0,       # 40-84% watched
    "completion_abandoned": -3.0, # <20% watched
    "rewatch": 4.0,               # Each additional watch
    "recency_halflife_days": 180, # Exponential decay half-life
}


# ── Data structures ──────────────────────────────────────────────

@dataclass
class GenreAffinity:
    """Weighted genre preference for a user."""
    genre: str
    score: float = 0.0        # Normalized 0.0-1.0
    raw_score: float = 0.0    # Pre-normalization
    watch_count: int = 0      # How many titles with this genre
    avg_completion: float = 0.0
    total_hours: float = 0.0


@dataclass
class KeywordAffinity:
    """Weighted TMDB keyword preference."""
    keyword: str
    score: float = 0.0
    occurrence_count: int = 0


@dataclass
class PersonnelAffinity:
    """Director/actor preference from watch patterns."""
    name: str
    role: str                  # "director" | "actor"
    score: float = 0.0
    title_count: int = 0
    avg_completion: float = 0.0


@dataclass
class TasteProfile:
    """Complete taste profile for a user across one or all domains."""
    user_id: str
    username: str
    domain: str                # "movies" | "tv" | "anime" | "all"
    built_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_watched: int = 0
    total_hours: float = 0.0
    avg_completion: float = 0.0
    rewatch_count: int = 0
    # Vectors
    genres: list[GenreAffinity] = field(default_factory=list)
    keywords: list[KeywordAffinity] = field(default_factory=list)
    personnel: list[PersonnelAffinity] = field(default_factory=list)
    # Negative signals
    avoided_genres: list[GenreAffinity] = field(default_factory=list)
    avoided_keywords: list[KeywordAffinity] = field(default_factory=list)

    def top_genres(self, n: int = 8) -> list[GenreAffinity]:
        return sorted(self.genres, key=lambda g: g.score, reverse=True)[:n]

    def top_keywords(self, n: int = 15) -> list[KeywordAffinity]:
        return sorted(self.keywords, key=lambda k: k.score, reverse=True)[:n]

    def top_personnel(self, n: int = 10) -> list[PersonnelAffinity]:
        return sorted(self.personnel, key=lambda p: p.score, reverse=True)[:n]

    def genre_score(self, genre: str) -> float:
        """Look up score for a specific genre."""
        for g in self.genres:
            if g.genre == genre:
                return g.score
        return 0.0

    def keyword_score(self, keyword: str) -> float:
        """Look up score for a specific keyword."""
        for k in self.keywords:
            if k.keyword == keyword:
                return k.score
        return 0.0


# ── Plex library → domain mapping ────────────────────────────────
# Maps Tautulli library section IDs to recommendation domains.
# These come from the verified Plex libraries on Ray's server.

DEFAULT_LIBRARY_DOMAINS = {
    # Movies
    "14": "movies",    # Movies
    "20": "movies",    # Kinderfilme
    # TV
    "2": "tv",         # TV Series
    "7": "tv",         # Kinderserien
    # Anime
    "10": "anime",     # Anime
    "15": "anime",     # Anime-Ecchi
    "17": "anime",     # Anime-Hentai
}


# ── Vector normalization ─────────────────────────────────────────

def normalize_taste_vectors(
    genre_scores: dict,
    keyword_scores: dict,
    personnel_scores: dict,
    username: str,
    domain: str,
    total_watched: int,
    total_hours: float,
    completions: list[float],
    rewatch_count: int,
) -> "TasteProfile":
    """Normalize raw score dicts into TasteProfile with 0.0–1.0 vectors."""
    max_g = max((g["score"] for g in genre_scores.values()), default=1.0) or 1.0
    max_k = max((k["score"] for k in keyword_scores.values()), default=1.0) or 1.0
    max_p = max((p["score"] for p in personnel_scores.values()), default=1.0) or 1.0

    genres_list, avoided_genres = [], []
    for genre, data in genre_scores.items():
        normalized = data["score"] / max_g
        avg_comp = sum(data["completions"]) / len(data["completions"]) if data["completions"] else 0
        ga = GenreAffinity(
            genre=genre,
            score=round(max(0.0, min(1.0, normalized)), 3),
            raw_score=round(data["score"], 2),
            watch_count=data["count"],
            avg_completion=round(avg_comp, 1),
            total_hours=round(data["hours"], 1),
        )
        (avoided_genres if data["score"] < 0 else genres_list).append(ga)

    keywords_list, avoided_keywords = [], []
    for kw, data in keyword_scores.items():
        normalized = data["score"] / max_k
        ka = KeywordAffinity(
            keyword=kw,
            score=round(max(0.0, min(1.0, normalized)), 3),
            occurrence_count=data["count"],
        )
        (avoided_keywords if data["score"] < 0 else keywords_list).append(ka)

    personnel_list = []
    for key, data in personnel_scores.items():
        role, name = key.split(":", 1)
        normalized = data["score"] / max_p
        avg_comp = sum(data["completions"]) / len(data["completions"]) if data["completions"] else 0
        personnel_list.append(PersonnelAffinity(
            name=name, role=role,
            score=round(max(0.0, min(1.0, normalized)), 3),
            title_count=data["count"],
            avg_completion=round(avg_comp, 1),
        ))

    avg_completion = sum(completions) / len(completions) if completions else 0.0

    return TasteProfile(
        user_id=username, username=username, domain=domain,
        total_watched=total_watched,
        total_hours=round(total_hours, 1),
        avg_completion=round(avg_completion, 1),
        rewatch_count=rewatch_count,
        genres=genres_list, keywords=keywords_list,
        personnel=personnel_list,
        avoided_genres=avoided_genres,
        avoided_keywords=avoided_keywords,
    )
