"""Vitality scoring engine — computes library item health scores.

Five-signal composite: recency decay, play velocity, user breadth,
recommendation frequency, niche genre adjustment. Each signal normalized
0-100, weighted into a composite that determines zone placement.

Pure scoring logic — no DB writes. Called by vitality_scheduler.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Scoring Weights (admin-configurable defaults) ────────────────

DEFAULT_WEIGHTS = {
    "recency": 0.30,
    "velocity": 0.25,
    "breadth": 0.20,
    "rec_frequency": 0.10,
    "niche": 0.15,
}

DEFAULT_THRESHOLDS = {
    "healthy_min": 40.0,
    "sunset_min": 15.0,   # below this = dead zone
    "grace_period_days": 7,
    "vote_kick_pct": 0.60,
    "vote_quorum": 3,
    "reprieve_immunity_days": 30,
    "active_user_days": 90,  # configurable quorum
}

# Expected plays per month by media type (calibration baseline)
EXPECTED_PLAYS = {"movie": 0.5, "show": 1.5}
RECENCY_HALF_LIFE = 90  # days


@dataclass
class VitalitySignals:
    """Individual signal scores for a single library item."""
    tmdb_id: int
    media_type: str
    servarr_id: Optional[int] = None
    title: str = ""
    poster_path: Optional[str] = None

    recency: float = 0.0
    velocity: float = 0.0
    breadth: float = 0.0
    rec_frequency: float = 0.0
    niche: float = 0.0
    composite: float = 0.0
    zone: str = "healthy"


@dataclass
class PlayStats:
    """Aggregated play data for a single item across all users."""
    tmdb_id: int
    media_type: str
    last_played: Optional[datetime] = None
    total_plays: int = 0
    unique_users: set = field(default_factory=set)
    monthly_plays: list = field(default_factory=list)  # [count_month_0, ..., count_month_5]


def score_recency(last_played: Optional[datetime], now: datetime) -> float:
    """Exponential decay: 100 × e^(-days / half_life). Never played = 0."""
    if not last_played:
        return 0.0
    days = max(0, (now - last_played).total_seconds() / 86400)
    return 100.0 * math.exp(-days / RECENCY_HALF_LIFE)


def score_velocity(monthly_plays: list[int], media_type: str) -> float:
    """Play velocity with trend detection.

    monthly_plays: [newest_month, ..., oldest_month] — up to 6 months.
    """
    if not monthly_plays or sum(monthly_plays) == 0:
        return 0.0

    expected = EXPECTED_PLAYS.get(media_type, 0.5)
    avg_per_month = sum(monthly_plays) / max(len(monthly_plays), 1)
    base = min(100.0, (avg_per_month / expected) * 50.0)

    # Trend detection: compare first half vs second half
    if len(monthly_plays) >= 4:
        recent = sum(monthly_plays[: len(monthly_plays) // 2])
        older = sum(monthly_plays[len(monthly_plays) // 2 :])
        if recent > older * 1.3:
            trend_bonus = 20.0  # growing
        elif recent < older * 0.7:
            trend_bonus = -20.0  # declining
        else:
            trend_bonus = 0.0
    else:
        trend_bonus = 0.0

    return max(0.0, min(100.0, base + trend_bonus))


def score_breadth(unique_watchers: int, active_users: int) -> float:
    """Ratio of unique watchers to active users, scaled ×200."""
    if active_users <= 0:
        return 0.0
    return min(100.0, (unique_watchers / active_users) * 200.0)


def score_rec_frequency(appearances_30d: int) -> float:
    """Recommendation appearances in last 30 days, ×10 scaling."""
    return min(100.0, appearances_30d * 10.0)


def score_niche(
    item_genres: list[str],
    genre_counts: dict[str, int],
    total_library: int,
    base_play_count: int,
) -> float:
    """Genre rarity bonus — niche titles need fewer plays to be healthy.

    genre_counts: {genre_name: count_of_items_with_that_genre}
    """
    if not item_genres or total_library <= 0:
        return min(100.0, base_play_count * 10.0)

    # Average rarity across the item's genres
    rarities = []
    for g in item_genres:
        count = genre_counts.get(g, 0)
        rarity = 1.0 - (count / total_library)
        rarities.append(rarity)

    avg_rarity = sum(rarities) / len(rarities) if rarities else 0.0
    niche_bonus = avg_rarity * 50.0
    base = min(50.0, base_play_count * 5.0)  # cap base at 50

    return min(100.0, base + niche_bonus)


def compute_vitality(
    signals: VitalitySignals,
    weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
) -> VitalitySignals:
    """Compute composite score and assign zone from individual signals."""
    w = weights or DEFAULT_WEIGHTS
    t = thresholds or DEFAULT_THRESHOLDS

    signals.composite = (
        signals.recency * w["recency"]
        + signals.velocity * w["velocity"]
        + signals.breadth * w["breadth"]
        + signals.rec_frequency * w["rec_frequency"]
        + signals.niche * w["niche"]
    )

    if signals.composite >= t["healthy_min"]:
        signals.zone = "healthy"
    elif signals.composite >= t["sunset_min"]:
        signals.zone = "sunset"
    else:
        signals.zone = "dead"

    return signals


def estimate_redownload_tier(
    tmdb_popularity: Optional[float],
    year: Optional[int],
    original_language: Optional[str],
    now_year: int = 2026,
) -> str:
    """Heuristic re-download ETA tier based on TMDB metadata.

    Returns: instant | hours | days | weeks | rare
    """
    pop = tmdb_popularity or 0.0
    age = (now_year - year) if year else 50
    is_english = (original_language or "").lower() in ("en", "")

    if pop > 50 and age < 2 and is_english:
        return "instant"
    if pop > 20 and age < 5:
        return "hours"
    if pop > 5 and age < 15:
        return "days"
    if pop > 1 or (not is_english and pop > 0.5):
        return "weeks"
    return "rare"
