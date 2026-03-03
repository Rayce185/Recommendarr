"""AI-enhanced mood parsing — LLM translates natural language to MoodVector.

Falls back to deterministic keyword mapper when:
- AI is disabled
- LLM call fails
- Response can't be parsed

The LLM receives the user's mood text and returns structured JSON matching
the MoodVector schema. This handles nuance the keyword mapper can't:
- "something like Lost in Translation but funnier"
- "a movie my 80-year-old grandma would enjoy"
- "I just got dumped, distract me"
"""

import json
import logging
from typing import Optional

from app.services.ai_config import get_ai_config
from app.services.ai_client import llm_complete
from app.services.mood_mapper import MoodVector, parse_mood

logger = logging.getLogger(__name__)

MOOD_SYSTEM_PROMPT = """You are a movie/TV recommendation mood parser. Given a user's natural language description of what they want to watch, extract structured parameters.

Respond ONLY with a JSON object (no markdown, no explanation). Fields (all optional — omit if not relevant):

{
  "genre_boost": {"Genre": 0.0-1.0},    // TMDB genres with relevance weight
  "genre_block": ["Genre"],               // genres to exclude
  "keyword_boost": ["keyword"],           // TMDB-style keywords to prefer
  "keyword_block": ["keyword"],           // keywords to exclude
  "domain_filter": ["movies","tv","anime"], // empty = all types
  "min_rating": 7.5,                      // minimum TMDB rating (only if user wants "good"/"highly rated")
  "max_runtime": 100,                     // max minutes (only if user wants "short")
  "min_runtime": 150,                     // min minutes (only if user wants "long"/"epic")
  "year_range": [1980, 1989],            // [start, end] year range
  "confidence": 0.0-1.0                  // how well you understood the request
}

Valid TMDB genres: Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Mystery, Romance, Science Fiction, TV Movie, Thriller, War, Western.

Be generous with genre weights. A request like "something fun" should boost Comedy (0.7), Adventure (0.4), Animation (0.3).
A request like "I just got dumped" should boost Comedy (0.5), Romance (0.3), Drama (0.4) — comfort viewing.
Parse negations: "not horror" → genre_block: ["Horror"]."""


async def parse_mood_ai(text: str) -> MoodVector:
    """Parse mood with LLM if enabled, fall back to deterministic parser.

    Returns a MoodVector either way — callers don't need to know which path ran.
    """
    cfg = get_ai_config()

    if not cfg.is_llm_enabled or not cfg.features.ai_mood:
        return parse_mood(text)

    # Try LLM
    try:
        response = await llm_complete(
            prompt=f'Parse this mood/request into JSON:\n\n"{text}"',
            system=MOOD_SYSTEM_PROMPT,
            config=cfg,
        )

        if not response:
            logger.warning("AI mood: empty LLM response, falling back")
            return parse_mood(text)

        vector = _parse_llm_response(response, text)
        if vector:
            logger.info(f"AI mood parsed: {len(vector.genre_boost)} genres, confidence={vector.confidence:.2f}")
            return vector

    except Exception as e:
        logger.error(f"AI mood parsing failed: {e}")

    # Fallback
    logger.info("AI mood: falling back to keyword parser")
    return parse_mood(text)


def _parse_llm_response(response: str, original_text: str) -> Optional[MoodVector]:
    """Parse LLM JSON response into a MoodVector."""
    try:
        # Strip markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)

        vector = MoodVector()
        vector.genre_boost = {k: min(1.0, float(v)) for k, v in data.get("genre_boost", {}).items()}
        vector.genre_block = data.get("genre_block", [])
        vector.keyword_boost = data.get("keyword_boost", [])
        vector.keyword_block = data.get("keyword_block", [])
        vector.domain_filter = data.get("domain_filter", [])
        vector.confidence = float(data.get("confidence", 0.5))

        if "min_rating" in data and data["min_rating"]:
            vector.min_rating = float(data["min_rating"])
        if "max_runtime" in data and data["max_runtime"]:
            vector.max_runtime = int(data["max_runtime"])
        if "min_runtime" in data and data["min_runtime"]:
            vector.min_runtime = int(data["min_runtime"])
        if "year_range" in data and data["year_range"] and len(data["year_range"]) == 2:
            vector.year_range = tuple(data["year_range"])

        # Remove blocked genres from boost
        for blocked in vector.genre_block:
            vector.genre_boost.pop(blocked, None)

        return vector

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning(f"AI mood: failed to parse LLM response: {e}")
        logger.debug(f"LLM response was: {response[:500]}")
        return None
