"""Mood Keyword Mapper — structured mood language → genre/keyword weights.

Translates natural language mood descriptions into TMDB genre and keyword
weights WITHOUT requiring an LLM. Uses a curated vocabulary of ~200 mood
words mapped to genre affinities and TMDB keyword preferences.

Architecture:
  1. Tokenize input → extract mood tokens
  2. Detect negations ("not", "no", "without", "but not")
  3. Map positive tokens → genre boosts + keyword boosts
  4. Map negated tokens → genre blocks + keyword blocks
  5. Detect "like <title>" patterns → Seerr similar lookup
  6. Return a MoodVector that the recommendation engine can apply

No LLM. No embeddings. Deterministic. Works offline.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.services.mood_vocab import MOOD_VOCAB, MOOD_PRESETS  # noqa: F401 — re-exported

logger = logging.getLogger(__name__)


@dataclass
class MoodVector:
    """Output of mood parsing — weights for the recommendation engine."""
    genre_boost: dict[str, float] = field(default_factory=dict)    # genre → weight (0.0-1.0)
    genre_block: list[str] = field(default_factory=list)           # genres to exclude
    keyword_boost: list[str] = field(default_factory=list)         # TMDB keywords to prefer
    keyword_block: list[str] = field(default_factory=list)         # TMDB keywords to exclude
    domain_filter: list[str] = field(default_factory=list)         # ["movies","tv","anime"] — empty = all
    similar_to_tmdb: list[int] = field(default_factory=list)       # TMDB IDs for "like X" queries
    min_rating: Optional[float] = None                              # "highly rated" → 7.5+
    max_runtime: Optional[int] = None                               # "short" → <100 min
    min_runtime: Optional[int] = None                               # "long epic" → 150+ min
    year_range: Optional[tuple[int, int]] = None                    # "80s" → (1980, 1989)
    confidence: float = 0.0                                         # How well we parsed this (0-1)
    unparsed_tokens: list[str] = field(default_factory=list)       # Tokens we couldn't map


# Negation patterns — these flip the next token to block instead of boost
NEGATION_PATTERNS = re.compile(
    r'\b(not|no|without|except|but\s+not|anything\s+but|nothing|never|exclude|avoid|skip|minus|non)\b',
    re.IGNORECASE,
)

# "like <title>" pattern — extracts title for Seerr similar lookup
LIKE_PATTERN = re.compile(
    r'\blike\s+["\']?(.+?)["\']?\s*$|\bsimilar\s+to\s+["\']?(.+?)["\']?\s*$',
    re.IGNORECASE,
)


def parse_mood(text: str) -> MoodVector:
    """Parse a natural language mood description into a MoodVector.

    Examples:
        "something tense but not horror" → boost Thriller/Mystery, block Horror
        "fun anime for tonight" → boost Comedy/Action, domain anime
        "slow burn cerebral sci-fi like Interstellar" → boost SciFi/Drama, keywords, similar_to
        "80s action" → boost Action, era 1980-1989
    """
    vector = MoodVector()
    matched_count = 0

    # Check for "like X" / "similar to X" pattern first
    like_match = LIKE_PATTERN.search(text)
    like_title = None
    if like_match:
        like_title = (like_match.group(1) or like_match.group(2)).strip()
        # Remove the "like X" part from further processing
        text = text[:like_match.start()].strip()

    # Normalize text
    cleaned = text.lower().strip()
    cleaned = re.sub(r'[^\w\s\-]', ' ', cleaned)  # Remove punctuation except hyphens
    cleaned = re.sub(r'\s+', ' ', cleaned)          # Collapse whitespace

    # Find negation boundaries
    # Split text into segments at negation words
    parts = NEGATION_PATTERNS.split(cleaned)
    negated = False

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        # Check if this part IS a negation word
        if NEGATION_PATTERNS.fullmatch(part):
            negated = True
            continue

        # Tokenize this segment
        tokens = part.split()

        for token in tokens:
            token = token.strip().lower().replace("_", "-")
            if not token or len(token) < 2:
                continue

            # Skip filler words
            if token in ("something", "anything", "a", "an", "the", "for",
                         "tonight", "today", "me", "some", "very", "really",
                         "kind", "of", "bit", "with", "and", "or", "that",
                         "this", "want", "need", "feel", "like", "i", "im",
                         "i'm", "we", "us", "maybe", "perhaps", "please",
                         "recommend", "suggestion", "give", "find", "looking",
                         "mood", "vibe", "type", "style"):
                continue

            # Compound token attempts (e.g., "sci fi" → "sci-fi")
            entry = MOOD_VOCAB.get(token)

            if entry:
                matched_count += 1
                if negated:
                    # Block these genres/keywords
                    for genre in entry.get("genres", {}):
                        if genre not in vector.genre_block:
                            vector.genre_block.append(genre)
                    for kw in entry.get("keywords", []):
                        if kw not in vector.keyword_block:
                            vector.keyword_block.append(kw)
                else:
                    # Boost these genres/keywords
                    for genre, weight in entry.get("genres", {}).items():
                        vector.genre_boost[genre] = min(1.0, vector.genre_boost.get(genre, 0.0) + weight)
                    for kw in entry.get("keywords", []):
                        if kw not in vector.keyword_boost:
                            vector.keyword_boost.append(kw)
                    # Domain hint
                    if "domain" in entry:
                        dom = entry["domain"]
                        if dom not in vector.domain_filter:
                            vector.domain_filter.append(dom)
                    # Era/runtime/rating constraints
                    if "era" in entry:
                        vector.year_range = entry["era"]
                    if "max_runtime" in entry:
                        vector.max_runtime = entry["max_runtime"]
                    if "min_runtime" in entry:
                        vector.min_runtime = entry["min_runtime"]
                    if "min_rating" in entry:
                        vector.min_rating = entry["min_rating"]
            else:
                # Try as direct TMDB keyword (pass through)
                vector.unparsed_tokens.append(token)

        # Reset negation after processing the segment following a negation word
        negated = False

    # Remove blocked genres from boost
    for blocked in vector.genre_block:
        vector.genre_boost.pop(blocked, None)

    # Remove blocked keywords from boost
    vector.keyword_boost = [k for k in vector.keyword_boost if k not in vector.keyword_block]

    # Confidence based on how many tokens we successfully mapped
    total_tokens = len(cleaned.split())
    filler_count = sum(1 for t in cleaned.split() if t in ("something","anything","a","an","the","for","tonight","today","me","some","very","really","i","im","and","or","that","this"))
    meaningful_tokens = max(1, total_tokens - filler_count)
    vector.confidence = min(1.0, matched_count / meaningful_tokens) if meaningful_tokens > 0 else 0.0

    # Attach like_title for downstream Seerr resolution
    if like_title:
        vector._like_title = like_title  # Resolved by recommendation engine

    return vector


def mood_to_explanation(vector: MoodVector) -> str:
    """Generate a human-readable explanation of how the mood was parsed."""
    parts = []
    if vector.genre_boost:
        top = sorted(vector.genre_boost.items(), key=lambda x: x[1], reverse=True)[:3]
        parts.append(f"Boosting: {', '.join(g for g, _ in top)}")
    if vector.genre_block:
        parts.append(f"Blocking: {', '.join(vector.genre_block)}")
    if vector.keyword_boost:
        parts.append(f"Keywords: {', '.join(vector.keyword_boost[:5])}")
    if vector.domain_filter:
        parts.append(f"Domain: {', '.join(vector.domain_filter)}")
    if vector.year_range:
        parts.append(f"Era: {vector.year_range[0]}-{vector.year_range[1]}")
    if vector.min_rating:
        parts.append(f"Min rating: {vector.min_rating}")
    if vector.unparsed_tokens:
        parts.append(f"Unrecognized: {', '.join(vector.unparsed_tokens[:3])}")
    return " · ".join(parts) if parts else "No mood signals detected"
