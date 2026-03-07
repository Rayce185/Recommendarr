"""Scoring and filtering logic for the recommendation engine.

Pure functions — no service dependencies, no self.
Takes profile, mood, overrides as explicit parameters.
"""

import logging
from typing import Optional

from app.services.rec_types import SCORE_WEIGHTS
from app.services.taste_profiler import TasteProfile
from app.services.mood_mapper import MoodVector
from app.services.profile_overrides import ProfileOverrides

logger = logging.getLogger(__name__)


# Section-to-genre mapping for library exclusion derivation
_SECTION_GENRE_MAP: dict[str, set[str]] = {
    "anime":        {"anime"},
    "anime-ecchi":  {"anime"},
    "anime-hentai": {"anime"},
}


def apply_filters(candidates: list[dict], req) -> list[dict]:
    """Apply genre, library section, and domain filters to candidate list.

    Handles:
    - Genre exclusion (explicit + derived from library section exclusions)
    - Genre inclusion (whitelist)
    - Library section exclusion (via Plex client)
    - Domain filtering (movies/tv/anime)
    """
    filtered = candidates

    # Derive genre exclusions from library section exclusions
    derived_genres: set[str] = set()
    if req.exclude_libraries:
        for lib in req.exclude_libraries:
            extra = _SECTION_GENRE_MAP.get(lib.lower(), set())
            derived_genres |= extra

    # Genre exclusion (explicit + derived)
    excl_genres = {g.lower() for g in req.exclude_genres} if req.exclude_genres else set()
    excl_genres |= derived_genres
    if excl_genres:
        filtered = [
            c for c in filtered
            if not any(
                (g.lower() if isinstance(g, str) else g.get("name", "").lower()) in excl_genres
                for g in c.get("genres", [])
            )
        ]

    # Genre inclusion (keep only items with at least one included genre)
    if req.include_genres:
        incl = {g.lower() for g in req.include_genres}
        filtered = [
            c for c in filtered
            if any(
                (g.lower() if isinstance(g, str) else g.get("name", "").lower()) in incl
                for g in c.get("genres", [])
            )
        ]

    # Library section exclusion (requires Plex client)
    if req.exclude_libraries:
        from app.services.factory import get_stack
        stack = get_stack()
        if stack.plex:
            filtered = [
                c for c in filtered
                if not stack.plex.is_in_section(
                    c.get("tmdb_id", 0), c.get("media_type", "movie"),
                    req.exclude_libraries,
                )
            ]

    # Single genre filter (from URL param)
    if req.genre_filter:
        target = req.genre_filter.lower()
        filtered = [c for c in filtered if any(
            g.lower() == target for g in c.get("genres", [])
        )]

    # Domain filter
    if req.domain == "movies":
        filtered = [c for c in filtered if c.get("media_type") == "movie"]
    elif req.domain == "tv":
        filtered = [c for c in filtered if c.get("media_type") == "tv"]
    elif req.domain == "anime":
        filtered = [c for c in filtered if "Anime" in c.get("genres", [])
                     or any("anime" in k.lower() for k in c.get("keywords", []))]

    return filtered


def score_candidate(
    candidate: dict,
    profile: TasteProfile,
    mood: Optional[MoodVector] = None,
    overrides: Optional[ProfileOverrides] = None,
    pulse_events: Optional[list[dict]] = None,
) -> tuple[float, dict, list[str]]:
    """Score a single candidate against a taste profile, optional mood, pulse events, and user overrides.

    Returns (total_score, breakdown_dict, explanation_signals).
    """
    breakdown = {}
    signals = []

    # 1. Genre match
    c_genres = candidate.get("genres", [])
    if c_genres and profile.genres:
        genre_scores = [profile.genre_score(g) for g in c_genres]
        genre_match = max(genre_scores) if genre_scores else 0.0
        breakdown["genre"] = genre_match
        if genre_match > 0.7:
            top_genre = c_genres[genre_scores.index(max(genre_scores))] if genre_scores else ""
            signals.append(f"Strong {top_genre} affinity")
    else:
        breakdown["genre"] = 0.0

    # 1b. Profile overrides for genres
    if overrides:
        for g in c_genres:
            if g in overrides.genre_blocks:
                return 0.0, breakdown, [f"Blocked genre: {g}"]
        genre_boost_total = sum(overrides.genre_boosts.get(g, 0) for g in c_genres)
        if c_genres:
            avg_boost = genre_boost_total / len(c_genres)
            breakdown["genre"] = max(0.0, min(1.0, breakdown.get("genre", 0) + avg_boost))

    # 2. Keyword match
    c_keywords = candidate.get("keywords", [])
    if c_keywords and profile.keywords:
        kw_scores = [profile.keyword_score(k) for k in c_keywords]
        kw_match = (sum(s for s in kw_scores if s > 0) / max(len(c_keywords), 1))
        breakdown["keyword"] = min(1.0, kw_match * 2)
        if kw_match > 0.3:
            matched = [k for k, s in zip(c_keywords, kw_scores) if s > 0.3][:2]
            if matched:
                signals.append(f"Keywords: {', '.join(matched)}")
    else:
        breakdown["keyword"] = 0.0

    # 2b. Keyword overrides
    if overrides:
        for kw in c_keywords:
            if kw in overrides.keyword_blocks:
                breakdown["keyword"] = max(0.0, breakdown.get("keyword", 0) - 0.3)
            if kw in overrides.keyword_boosts:
                breakdown["keyword"] = min(1.0, breakdown.get("keyword", 0) + 0.2)

    # 2c. Feedback-based genre adjustments
    liked_g = getattr(overrides, '_feedback_liked_genres', {}) if overrides else {}
    disliked_g = getattr(overrides, '_feedback_disliked_genres', {}) if overrides else {}
    if liked_g:
        for g in c_genres:
            if g in liked_g:
                boost = min(0.15, liked_g[g] * 0.05)
                breakdown["genre"] = min(1.0, breakdown.get("genre", 0) + boost)
                if boost >= 0.1:
                    signals.append(f"Liked similar {g} titles")
    if disliked_g:
        for g in c_genres:
            if g in disliked_g:
                penalty = min(0.15, disliked_g[g] * 0.05)
                breakdown["genre"] = max(0.0, breakdown.get("genre", 0) - penalty)

    # 3. Rating quality
    vote_avg = candidate.get("vote_average", 0) or 0
    rating_score = min(1.0, max(0.0, (vote_avg - 5.0) / 4.5))
    breakdown["rating"] = rating_score
    if vote_avg >= 8.0:
        signals.append(f"Highly rated ({vote_avg:.1f})")

    # 4. Personnel match
    c_directors = candidate.get("directors", [])
    c_cast = candidate.get("cast", [])
    personnel_score = 0.0
    for name in c_directors:
        for p in profile.personnel:
            if p.name == name and p.role == "director":
                personnel_score = max(personnel_score, p.score)
                if p.score > 0.5:
                    signals.append(f"Director: {name}")
    for name in c_cast[:3]:
        for p in profile.personnel:
            if p.name == name and p.role == "actor":
                personnel_score = max(personnel_score, p.score * 0.7)
    breakdown["personnel"] = personnel_score

    # 5. Popularity (normalized)
    popularity = candidate.get("popularity", 0) or 0
    breakdown["popularity"] = min(1.0, popularity / 100)

    # 6. Mood alignment
    mood_score = 0.0
    if mood:
        for genre in c_genres:
            if genre in mood.genre_boost:
                mood_score += mood.genre_boost[genre]
            if genre in mood.genre_block:
                return 0.0, breakdown, ["Blocked by mood filter"]

        kw_hits = sum(1 for kw in c_keywords if kw in mood.keyword_boost)
        kw_blocks = sum(1 for kw in c_keywords if kw in mood.keyword_block)
        mood_score += kw_hits * 0.4
        mood_score -= kw_blocks * 0.5
        if mood.keyword_boost and kw_hits == 0:
            mood_score -= 0.4

        runtime = candidate.get("runtime") or 0
        if mood.max_runtime and runtime > mood.max_runtime:
            mood_score -= 0.5
        if mood.min_runtime and runtime < mood.min_runtime:
            mood_score -= 0.3

        year = candidate.get("year") or 0
        if mood.year_range:
            if year < mood.year_range[0] or year > mood.year_range[1]:
                mood_score -= 0.5

        if mood.min_rating and vote_avg < mood.min_rating:
            mood_score -= 0.3

        mood_score = max(0.0, min(1.0, mood_score))
        breakdown["mood"] = mood_score
    else:
        breakdown["mood"] = 0.5

    # 7. Cultural Pulse alignment
    pulse_score = 0.0
    if pulse_events:
        c_genre_lower = {(g.lower() if isinstance(g, str) else g.get("name", "").lower()) for g in c_genres}
        c_kw_lower = {k.lower() for k in c_keywords}
        best_boost = 0.0
        best_theme = ""
        for event in pulse_events:
            mapping = event.get("mapping")
            if not mapping:
                continue
            event_genres = {g.lower() for g in (mapping.get("genres") or [])}
            event_keywords = {k.lower() for k in (mapping.get("keywords") or [])}
            genre_overlap = len(c_genre_lower & event_genres)
            kw_overlap = len(c_kw_lower & event_keywords)
            if genre_overlap > 0 or kw_overlap > 0:
                hit_strength = min(1.0, genre_overlap * 0.4 + kw_overlap * 0.2)
                if hit_strength > best_boost:
                    best_boost = hit_strength
                    best_theme = event.get("title", "")
        if best_boost > 0:
            pulse_score = best_boost
            if best_theme:
                label = best_theme if best_theme.startswith("Trending") else f"Trending: {best_theme}"
                signals.append(label)
    breakdown["pulse"] = pulse_score

    # Weighted total
    total = (
        breakdown.get("genre", 0) * SCORE_WEIGHTS["genre_match"]
        + breakdown.get("keyword", 0) * SCORE_WEIGHTS["keyword_match"]
        + breakdown.get("rating", 0) * SCORE_WEIGHTS["rating_quality"]
        + breakdown.get("personnel", 0) * SCORE_WEIGHTS["personnel_match"]
        + breakdown.get("popularity", 0) * SCORE_WEIGHTS["popularity"]
        + breakdown.get("mood", 0.5) * SCORE_WEIGHTS["mood_alignment"]
        + breakdown.get("pulse", 0) * SCORE_WEIGHTS["pulse_alignment"]
    )

    return round(total, 4), breakdown, signals
