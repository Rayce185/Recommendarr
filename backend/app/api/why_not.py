"""Why Not? — Negative transparency for recommendations.

Explains why a specific title wasn't recommended to a user.
Returns per-signal score breakdown with human-readable assessments.
"""

import logging
from fastapi import APIRouter, Query, HTTPException

from app.services.factory import get_stack
from app.services.cache import get_cache
from app.services.rec_scoring import score_candidate
from app.services.rec_types import SCORE_WEIGHTS
from app.services.profile_overrides import get_override_store
from app.services.feedback import get_feedback_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _assess(score: float, label: str) -> dict:
    """Map a 0-1 score to a human assessment."""
    if score >= 0.8:
        level, emoji = "strong_match", "✅"
    elif score >= 0.5:
        level, emoji = "moderate_match", "🟡"
    elif score >= 0.2:
        level, emoji = "weak_match", "🟠"
    else:
        level, emoji = "no_match", "❌"
    return {"label": label, "score": round(score, 3), "level": level, "emoji": emoji}


@router.get("/why-not/{tmdb_id}")
async def why_not(
    tmdb_id: int,
    username: str = Query(..., description="Username to check against"),
    media_type: str = Query("movie", pattern="^(movie|tv)$"),
):
    """Explain why a title wasn't recommended.

    Returns per-signal breakdown, weighted total, and
    comparison to the user's recommendation threshold.
    """
    stack = get_stack()
    cache = get_cache()

    # 1. Build or fetch taste profile
    profile = cache.get_profile(username, "all")
    if not profile:
        try:
            profile = await stack.profiler.build_profile(
                username=username, domain="all",
                enrich_keywords=True, max_enrich=50,
            )
            cache.set_profile(username, "all", profile)
        except Exception as e:
            logger.warning(f"Why Not: could not build profile for {username}: {e}")
            # Fall back to empty profile — still show TMDB-based analysis
            from app.services.taste_models import TasteProfile
            profile = TasteProfile(user_id=username, username=username, domain='all')

    # 2. Fetch metadata for the title
    detail = None
    try:
        if stack.tmdb:
            detail = await stack.tmdb.get_detail(tmdb_id, media_type)
        elif stack.seerr:
            d = await stack.seerr.get_detail(tmdb_id, media_type)
            detail = {
                "tmdb_id": d.tmdb_id, "media_type": d.media_type,
                "title": d.title, "year": d.year,
                "genres": d.genres, "keywords": d.keywords,
                "vote_average": d.vote_average, "overview": d.overview,
                "directors": d.directors,
                "cast": [c.get("name", "") for c in d.cast[:5]] if d.cast else [],
                "runtime": d.runtime, "popularity": getattr(d, "popularity", 0),
                "original_language": d.original_language,
            }
    except Exception as e:
        raise HTTPException(404, f"Could not fetch metadata: {e}")

    if not detail:
        raise HTTPException(404, "Title not found")

    # Normalize TMDB detail dict format
    if isinstance(detail, dict):
        candidate = detail
    else:
        # TMDBClient returns a dict already
        candidate = detail

    # Ensure genres is a list of strings
    genres = candidate.get("genres", [])
    if genres and isinstance(genres[0], dict):
        genres = [g.get("name", "") for g in genres]
    candidate["genres"] = genres

    keywords = candidate.get("keywords", [])
    if keywords and isinstance(keywords[0], dict):
        keywords = [k.get("name", "") for k in keywords]
    candidate["keywords"] = keywords

    directors = candidate.get("directors", [])
    if directors and isinstance(directors[0], dict):
        directors = [d.get("name", "") for d in directors]
    candidate["directors"] = directors

    cast_raw = candidate.get("cast", [])
    cast_names = []
    for c in cast_raw[:5]:
        if isinstance(c, dict):
            cast_names.append(c.get("name", ""))
        else:
            cast_names.append(str(c))
    candidate["cast"] = cast_names

    # Get user overrides
    overrides = get_override_store().get(username)
    fb_store = get_feedback_store()
    liked_g, disliked_g = fb_store.get_genre_signals(username)
    if overrides:
        overrides._feedback_liked_genres = liked_g
        overrides._feedback_disliked_genres = disliked_g

    # 3. Score it
    total, breakdown, signals = score_candidate(candidate, profile, overrides=overrides)

    # 4. Get threshold — what score does the lowest recommended item have?
    threshold = 0.35  # reasonable default
    cached_recs = cache.get_recs(username, "tonight", "all")
    if cached_recs:
        scores = [r.get("score", 0) for r in cached_recs.get("recommendations", []) if r.get("score")]
        if scores:
            threshold = min(scores)

    # 5. Build detailed breakdown
    signal_details = []
    for key, weight in SCORE_WEIGHTS.items():
        # Map weight key to breakdown key
        bk_map = {
            "genre_match": "genre",
            "keyword_match": "keyword",
            "rating_quality": "rating",
            "personnel_match": "personnel",
            "popularity": "popularity",
            "mood_alignment": "mood",
            "cultural_pulse": "cultural_pulse",
            "collaborative": "collaborative",
        }
        bk = bk_map.get(key, key)
        raw = breakdown.get(bk, 0)
        weighted = round(raw * weight, 4)
        assessment = _assess(raw, key.replace("_", " ").title())
        assessment["raw_score"] = round(raw, 3)
        assessment["weight"] = weight
        assessment["weighted_score"] = weighted
        signal_details.append(assessment)

    # Sort by weighted impact (worst first — these explain the "why not")
    signal_details.sort(key=lambda s: s["weighted_score"])

    # 6. Generate human-readable reasons
    reasons = []
    for sig in signal_details:
        if sig["raw_score"] < 0.3:
            reasons.append(f"{sig['emoji']} {sig['label']}: {sig['raw_score']:.2f} — low match")
        elif sig["raw_score"] < 0.5:
            reasons.append(f"{sig['emoji']} {sig['label']}: {sig['raw_score']:.2f} — moderate gap")

    # Genre-specific insights
    user_top_genres = sorted(
        [(g.genre, g.score) for g in profile.genres],
        key=lambda x: x[1], reverse=True,
    )[:5]
    title_genres = genres
    overlap = [g for g in title_genres if any(ug[0] == g for ug in user_top_genres)]
    non_overlap = [g for g in title_genres if g not in overlap]
    if non_overlap:
        reasons.append(f"Genre gap: {', '.join(non_overlap)} not in your top preferences")
    if overlap:
        reasons.append(f"Genre match: {', '.join(overlap)} aligns with your taste")

    # Check if user dismissed or disliked
    fb = fb_store.get_action(username, tmdb_id)
    if fb == "down":
        reasons.insert(0, "👎 You previously disliked this title")
    elif fb == "dismiss":
        reasons.insert(0, "🚫 You previously dismissed this title")

    above_threshold = total >= threshold
    verdict = "above" if above_threshold else "below"

    return {
        "tmdb_id": tmdb_id,
        "title": candidate.get("title", ""),
        "media_type": media_type,
        "total_score": round(total, 4),
        "threshold": round(threshold, 4),
        "verdict": verdict,
        "verdict_text": (
            f"Score {total:.2f} is {'above' if above_threshold else 'below'} "
            f"the recommendation threshold ({threshold:.2f}). "
            + ("This title qualifies but may not have ranked high enough to appear in your limited results."
               if above_threshold
               else "The signals below explain the gap.")
        ),
        "signals": signal_details,
        "reasons": reasons,
        "user_top_genres": [{"genre": g, "score": round(s, 2)} for g, s in user_top_genres],
        "title_genres": title_genres,
        "user_feedback": fb,
    }
