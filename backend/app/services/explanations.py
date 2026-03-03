"""Explanation engine — Tier 1 template-based explanations.

Generates human-readable "Because you..." explanations without LLM calls.
Templates are selected based on which signals most influenced the recommendation.

Tier 1: Template-based (instant, zero cost) — implemented here
Tier 2: LLM-enhanced (richer, async) — future
Tier 3: LLM conversational (full natural language) — future
"""

import random
from typing import Optional

from app.services.recommender import Recommendation


# ── Template library ─────────────────────────────────────────────

TEMPLATES = {
    # Genre affinity is dominant signal
    "genre_match": [
        "You've been on a {genre} streak lately — this fits right in.",
        "Strong match for your {genre} taste.",
        "Your {genre} history says you'll like this one.",
        "Picked for your love of {genre}.",
    ],
    # Personnel match (director/actor)
    "director_match": [
        "Directed by {name} — you've finished {count} of their films.",
        "From {name}, whose work you consistently enjoy.",
        "Another {name} film — and you haven't seen this one yet.",
    ],
    "actor_match": [
        "Stars {name}, who you've watched in {count}+ titles.",
        "Featuring {name} — a reliable pick based on your history.",
        "{name} is in this, and you tend to finish their movies.",
    ],
    # Keyword/thematic match
    "theme_match": [
        "Shares themes with titles you've rated highly: {themes}.",
        "Thematically similar to your favorites — {themes}.",
        "If you liked the {themes} angle, this delivers more of that.",
    ],
    # High similarity (embedding distance)
    "similar_vibe": [
        "Similar vibe to titles you've loved recently.",
        "The DNA of this one closely matches your taste profile.",
        "Algorithmically, this is a strong match for your viewing patterns.",
    ],
    # Rediscover mode
    "rediscover": [
        "You loved this {time_ago} — time for a rewatch?",
        "Watched {time_ago} and finished it. Worth revisiting.",
        "A favorite from your history — it's been a while.",
    ],
    # Cold start / popularity
    "popular": [
        "Popular on the server — give it a try!",
        "Highly rated and widely watched here.",
        "A crowd favorite — solid starting point.",
    ],
    # Combined signals
    "multi_signal": [
        "Matches your {genre} taste, and features {name}.",
        "Strong {genre} match with themes you enjoy: {themes}.",
        "{name} directs this {genre} film — right up your alley.",
    ],
}

# i18n: German templates
TEMPLATES_DE = {
    "genre_match": [
        "Du hattest zuletzt einen {genre}-Lauf — das passt perfekt.",
        "Starke Übereinstimmung mit deinem {genre}-Geschmack.",
        "Basierend auf deiner {genre}-History sollte dir das gefallen.",
    ],
    "director_match": [
        "Regie: {name} — du hast {count} seiner Filme zu Ende geschaut.",
        "Von {name}, dessen Arbeit dir gefällt.",
    ],
    "actor_match": [
        "Mit {name}, den du in {count}+ Titeln gesehen hast.",
        "{name} spielt mit — basierend auf deiner History ein guter Tipp.",
    ],
    "theme_match": [
        "Thematisch ähnlich zu deinen Favoriten: {themes}.",
    ],
    "similar_vibe": [
        "Ähnliche Stimmung wie Titel, die dir gefallen haben.",
    ],
    "rediscover": [
        "Das hat dir {time_ago} gefallen — Zeit für ein Rewatch?",
    ],
    "popular": [
        "Beliebt auf dem Server — probier's mal!",
    ],
    "multi_signal": [
        "Passt zu deinem {genre}-Geschmack und hat {name} dabei.",
    ],
}

TEMPLATE_SETS = {
    "en": TEMPLATES,
    "de": TEMPLATES_DE,
}


class ExplanationEngine:
    """Generates template-based explanations for recommendations."""

    def __init__(self, language: str = "en"):
        self.templates = TEMPLATE_SETS.get(language, TEMPLATES)

    def explain(
        self,
        rec: Recommendation,
        profile: dict,
        mode: Optional[str] = None,
    ) -> str:
        """Generate a human-readable explanation for a recommendation.

        Selects template based on strongest signal, fills in specifics
        from the recommendation metadata and user profile.
        """
        mode = mode or rec.mode
        signals = rec.signals or {}

        # Rediscover mode has its own templates
        if mode == "rediscover":
            return self._explain_rediscover(rec, signals)

        # Cold start
        if signals.get("method") == "cold_start_popularity":
            return self._pick("popular")

        # Determine dominant signal
        genre_boost = signals.get("genre_boost", 0)
        similarity = signals.get("similarity", 0)

        # Check for personnel match
        personnel_match = self._find_personnel_match(rec, profile)
        theme_match = self._find_theme_match(rec, profile)

        # Multi-signal: genre + personnel
        if genre_boost > 0.2 and personnel_match:
            top_genre = self._top_matching_genre(rec, profile)
            return self._pick("multi_signal",
                genre=top_genre,
                name=personnel_match["name"],
                themes=theme_match or "",
            )

        # Personnel dominant
        if personnel_match and personnel_match.get("affinity", 0) > 0.5:
            template_key = "director_match" if personnel_match["type"] == "director" else "actor_match"
            return self._pick(template_key,
                name=personnel_match["name"],
                count=personnel_match.get("count", "several"),
            )

        # Genre dominant
        if genre_boost > 0.15:
            top_genre = self._top_matching_genre(rec, profile)
            return self._pick("genre_match", genre=top_genre)

        # Theme match
        if theme_match:
            return self._pick("theme_match", themes=theme_match)

        # High embedding similarity
        if similarity > 0.6:
            return self._pick("similar_vibe")

        # Fallback
        if genre_boost > 0:
            top_genre = self._top_matching_genre(rec, profile)
            return self._pick("genre_match", genre=top_genre)

        return self._pick("similar_vibe")

    def _explain_rediscover(self, rec: Recommendation, signals: dict) -> str:
        """Generate rediscover-mode explanation."""
        last_watched = signals.get("last_watched", "")
        if last_watched:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_watched)
                days = (datetime.now() - dt).days
                if days > 365:
                    time_ago = f"{days // 365} year{'s' if days > 730 else ''} ago"
                elif days > 30:
                    time_ago = f"{days // 30} months ago"
                else:
                    time_ago = "recently"
            except Exception:
                time_ago = "a while back"
        else:
            time_ago = "a while back"

        return self._pick("rediscover", time_ago=time_ago)

    def _find_personnel_match(self, rec: Recommendation, profile: dict) -> Optional[dict]:
        """Find if any cast/crew in this rec matches user's personnel affinities."""
        affinities = profile.get("personnel_affinities", {})
        if not affinities:
            return None

        # Check genres from TMDB cache (we don't have cast_crew on Recommendation directly)
        # This requires a DB lookup in practice — for now, use genre as proxy
        # TODO: enrich Recommendation with cast_crew from TmdbCache
        for name, score in affinities.items():
            if score > 0.4:
                return {"name": name, "type": "director", "affinity": score, "count": "several"}

        return None

    def _find_theme_match(self, rec: Recommendation, profile: dict) -> Optional[str]:
        """Find matching themes/keywords between rec and profile."""
        kw_affinities = profile.get("keyword_affinities", {})
        if not kw_affinities:
            return None

        # Match rec genres against keyword affinities as proxy
        matching = [kw for kw, score in kw_affinities.items() if score > 0.3]
        if matching:
            return ", ".join(matching[:3])
        return None

    def _top_matching_genre(self, rec: Recommendation, profile: dict) -> str:
        """Find the genre of this rec that has the highest user affinity."""
        affinities = profile.get("genre_affinities", {})
        if not rec.genres or not affinities:
            return rec.genres[0] if rec.genres else "this genre"

        best = max(rec.genres, key=lambda g: affinities.get(g, 0), default=rec.genres[0])
        return best

    def _pick(self, category: str, **kwargs) -> str:
        """Pick a random template from a category and fill in variables."""
        templates = self.templates.get(category, TEMPLATES.get(category, ["Great match for you."]))
        template = random.choice(templates)
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            # Fallback if template variables don't match
            return template.split("{")[0].strip() or "Recommended for you."
