"""AI-powered recommendation explanations.

When ai_explanations is enabled, replaces template-based explanation strings
with natural language "why we recommended this" from the LLM.

Single batched call for all results — keeps latency manageable.
Graceful fallback: if LLM fails, original explanations are preserved.
"""

import json
import logging
from typing import Optional

from app.services.ai_client import llm_complete
from app.services.ai_config import get_ai_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the recommendation engine for a personal media server.
Generate short, natural "why we picked this" explanations for each title.

Rules:
- One sentence per title, max 20 words
- Reference specific taste signals (genres they love, directors they follow, mood match)
- Sound like a knowledgeable friend, not a robot
- Never mention scores, percentages, or algorithms
- Use "you" naturally: "You've been into thrillers lately" not "Based on your profile"

Respond with ONLY a JSON array of strings, one explanation per title, in the same order.
Example: ["You loved Nolan's other work — this is his most ambitious.", "Perfect for your sci-fi mood tonight."]"""


async def generate_explanations(
    recs: list,
    profile_summary: str,
    mood_text: Optional[str] = None,
    max_items: int = 20,
) -> list[str]:
    """Generate AI explanations for a batch of recommendations.

    Args:
        recs: List of Recommendation objects (scored, with breakdown + signals)
        profile_summary: Short text summary of user's taste profile
        mood_text: Original mood input if any
        max_items: Max items to explain (limits prompt size + cost)

    Returns:
        List of explanation strings (same length as input recs).
        Falls back to original explanations on any failure.
    """
    cfg = get_ai_config()
    if not cfg.features.ai_explanations or not cfg.is_llm_enabled:
        return [r.explanation for r in recs]

    originals = [r.explanation for r in recs]
    batch = recs[:max_items]

    # Build compact item summaries for the prompt
    items = []
    for r in batch:
        entry = f"- {r.title} ({r.year or '?'}) [{', '.join(r.genres[:3])}]"
        if r.directors:
            entry += f" dir:{r.directors[0]}"
        if r.explanation_signals:
            entry += f" signals:{'; '.join(r.explanation_signals[:3])}"
        if r.score_breakdown:
            top = sorted(r.score_breakdown.items(), key=lambda x: x[1], reverse=True)[:2]
            entry += f" top:{','.join(f'{k}={v:.0%}' for k,v in top)}"
        items.append(entry)

    prompt = f"User taste: {profile_summary}\n"
    if mood_text:
        prompt += f"Current mood: {mood_text}\n"
    prompt += f"\nGenerate explanations for these {len(items)} titles:\n"
    prompt += "\n".join(items)

    try:
        raw = await llm_complete(prompt, system=SYSTEM_PROMPT)
        if not raw:
            return originals

        # Parse JSON array from response
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        explanations = json.loads(cleaned)
        if not isinstance(explanations, list):
            logger.warning("AI explanations: expected list, got %s", type(explanations))
            return originals

        # Merge: AI explanations for batch, originals for remainder
        result = []
        for i, r in enumerate(recs):
            if i < len(explanations) and explanations[i]:
                result.append(str(explanations[i]))
            else:
                result.append(originals[i])
        return result

    except json.JSONDecodeError as e:
        logger.warning("AI explanations: JSON parse failed: %s (raw: %s)", e, raw[:200] if raw else "None")
        return originals
    except Exception as e:
        logger.error("AI explanations failed: %s", e)
        return originals


def build_profile_summary(profile) -> str:
    """Build a compact text summary of a TasteProfile for the LLM prompt.

    Args:
        profile: TasteProfile object from taste_profiler.py
    """
    parts = []

    # Top genres
    top_genres = profile.top_genres(5)
    if top_genres:
        parts.append("Loves: " + ", ".join(g.genre for g in top_genres))

    # Top keywords
    top_kw = profile.top_keywords(5)
    if top_kw:
        parts.append("Themes: " + ", ".join(k.keyword for k in top_kw))

    # Top personnel
    top_people = profile.top_personnel(3)
    if top_people:
        parts.append("Favorites: " + ", ".join(f"{p.name} ({p.role})" for p in top_people))

    return " | ".join(parts) if parts else "New user, exploring"
