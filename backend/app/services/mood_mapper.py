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


# ── Mood Vocabulary ──────────────────────────────────────────────
# Format: token → {genres: {name: weight}, keywords: [tmdb_keywords]}
# Weights are additive — "tense dark thriller" stacks weights.

MOOD_VOCAB: dict[str, dict] = {
    # ── Emotional tones ──
    "tense":        {"genres": {"Thriller": 0.8, "Mystery": 0.5, "Crime": 0.4}, "keywords": ["suspenseful", "tension"]},
    "suspenseful":  {"genres": {"Thriller": 0.9, "Mystery": 0.6}, "keywords": ["suspenseful", "tension", "twist ending"]},
    "scary":        {"genres": {"Horror": 0.9, "Thriller": 0.4}, "keywords": ["supernatural", "haunted", "fear"]},
    "terrifying":   {"genres": {"Horror": 1.0, "Thriller": 0.3}, "keywords": ["supernatural", "survival", "fear"]},
    "creepy":       {"genres": {"Horror": 0.7, "Mystery": 0.4, "Thriller": 0.3}, "keywords": ["psychological", "supernatural", "eerie"]},
    "dark":         {"genres": {"Thriller": 0.6, "Crime": 0.5, "Drama": 0.4, "Horror": 0.3}, "keywords": ["dark", "neo-noir", "gritty"]},
    "gritty":       {"genres": {"Crime": 0.7, "Thriller": 0.5, "Drama": 0.4}, "keywords": ["gritty", "urban", "neo-noir"]},
    "intense":      {"genres": {"Action": 0.6, "Thriller": 0.7, "Drama": 0.5}, "keywords": ["intense", "suspenseful"]},
    "emotional":    {"genres": {"Drama": 0.9, "Romance": 0.4}, "keywords": ["tearjerker", "emotional", "tragedy"]},
    "sad":          {"genres": {"Drama": 0.8}, "keywords": ["tragedy", "tearjerker", "loss", "grief"]},
    "heartwarming": {"genres": {"Drama": 0.6, "Family": 0.5, "Comedy": 0.4}, "keywords": ["feel good", "friendship", "heartwarming"]},
    "uplifting":    {"genres": {"Drama": 0.5, "Comedy": 0.4, "Family": 0.3}, "keywords": ["feel good", "inspirational", "underdog"]},
    "feel-good":    {"genres": {"Comedy": 0.6, "Drama": 0.4, "Family": 0.4}, "keywords": ["feel good", "friendship", "heartwarming"]},
    "feelgood":     {"genres": {"Comedy": 0.6, "Drama": 0.4, "Family": 0.4}, "keywords": ["feel good", "friendship", "heartwarming"]},
    "cozy":         {"genres": {"Comedy": 0.5, "Family": 0.5, "Drama": 0.3}, "keywords": ["feel good", "small town", "friendship"]},
    "chill":        {"genres": {"Comedy": 0.5, "Drama": 0.4}, "keywords": ["slice of life", "feel good", "slow burn"]},
    "relaxing":     {"genres": {"Comedy": 0.5, "Drama": 0.3, "Documentary": 0.3}, "keywords": ["slice of life", "nature", "feel good"]},
    "fun":          {"genres": {"Comedy": 0.7, "Action": 0.4, "Adventure": 0.4}, "keywords": ["comedy", "buddy"]},
    "funny":        {"genres": {"Comedy": 0.9}, "keywords": ["comedy", "satire", "parody"]},
    "hilarious":    {"genres": {"Comedy": 1.0}, "keywords": ["slapstick", "comedy", "absurd"]},
    "witty":        {"genres": {"Comedy": 0.7, "Drama": 0.3}, "keywords": ["satire", "dark comedy", "dialogue"]},
    "romantic":     {"genres": {"Romance": 0.9, "Drama": 0.4, "Comedy": 0.3}, "keywords": ["love story", "romantic comedy", "romance"]},
    "love":         {"genres": {"Romance": 0.8, "Drama": 0.4}, "keywords": ["love story", "romance"]},
    "sexy":         {"genres": {"Romance": 0.6, "Drama": 0.5, "Thriller": 0.3}, "keywords": ["erotic", "seduction", "passion"]},
    "nostalgic":    {"genres": {"Drama": 0.5, "Comedy": 0.3, "Family": 0.3}, "keywords": ["nostalgia", "coming of age", "childhood"]},
    "trippy":       {"genres": {"Science Fiction": 0.6, "Fantasy": 0.4, "Drama": 0.3}, "keywords": ["surreal", "psychedelic", "mind-bending"]},
    "weird":        {"genres": {"Science Fiction": 0.4, "Fantasy": 0.3, "Comedy": 0.3, "Horror": 0.3}, "keywords": ["surreal", "absurd", "cult film"]},
    "epic":         {"genres": {"Action": 0.6, "Adventure": 0.6, "Drama": 0.5, "Fantasy": 0.4}, "keywords": ["epic", "battle", "war"]},
    "badass":       {"genres": {"Action": 0.9, "Thriller": 0.4, "Crime": 0.3}, "keywords": ["revenge", "martial arts", "vigilante"]},
    "brutal":       {"genres": {"Action": 0.7, "Crime": 0.5, "Horror": 0.4}, "keywords": ["violence", "gore", "revenge"]},

    # ── Genre-adjacent terms ──
    "action":       {"genres": {"Action": 1.0}, "keywords": []},
    "adventure":    {"genres": {"Adventure": 1.0}, "keywords": []},
    "comedy":       {"genres": {"Comedy": 1.0}, "keywords": []},
    "crime":        {"genres": {"Crime": 1.0}, "keywords": []},
    "documentary":  {"genres": {"Documentary": 1.0}, "keywords": []},
    "drama":        {"genres": {"Drama": 1.0}, "keywords": []},
    "family":       {"genres": {"Family": 1.0}, "keywords": []},
    "fantasy":      {"genres": {"Fantasy": 1.0}, "keywords": []},
    "history":      {"genres": {"History": 1.0}, "keywords": []},
    "historical":   {"genres": {"History": 0.9, "Drama": 0.3}, "keywords": ["based on true story", "period drama"]},
    "horror":       {"genres": {"Horror": 1.0}, "keywords": []},
    "mystery":      {"genres": {"Mystery": 1.0}, "keywords": []},
    "romance":      {"genres": {"Romance": 1.0}, "keywords": []},
    "scifi":        {"genres": {"Science Fiction": 1.0}, "keywords": []},
    "sci-fi":       {"genres": {"Science Fiction": 1.0}, "keywords": []},
    "science":      {"genres": {"Science Fiction": 0.8, "Documentary": 0.3}, "keywords": []},
    "thriller":     {"genres": {"Thriller": 1.0}, "keywords": []},
    "war":          {"genres": {"War": 1.0}, "keywords": ["battle", "military"]},
    "western":      {"genres": {"Western": 1.0}, "keywords": []},
    "musical":      {"genres": {"Music": 0.8}, "keywords": ["musical", "singing"]},
    "animated":     {"genres": {"Animation": 1.0}, "keywords": []},
    "animation":    {"genres": {"Animation": 1.0}, "keywords": []},

    # ── Thematic / Keyword-heavy terms ──
    "space":        {"genres": {"Science Fiction": 0.8}, "keywords": ["space", "space travel", "spacecraft", "astronaut"]},
    "alien":        {"genres": {"Science Fiction": 0.7, "Horror": 0.3}, "keywords": ["alien", "extraterrestrial", "invasion"]},
    "robot":        {"genres": {"Science Fiction": 0.7}, "keywords": ["robot", "artificial intelligence", "android"]},
    "ai":           {"genres": {"Science Fiction": 0.7, "Thriller": 0.3}, "keywords": ["artificial intelligence", "robot", "singularity"]},
    "cyberpunk":    {"genres": {"Science Fiction": 0.8, "Action": 0.3}, "keywords": ["cyberpunk", "dystopia", "hacker"]},
    "dystopia":     {"genres": {"Science Fiction": 0.7, "Drama": 0.3}, "keywords": ["dystopia", "post-apocalyptic", "totalitarianism"]},
    "dystopian":    {"genres": {"Science Fiction": 0.7, "Drama": 0.3}, "keywords": ["dystopia", "post-apocalyptic", "totalitarianism"]},
    "apocalyptic":  {"genres": {"Science Fiction": 0.6, "Action": 0.4}, "keywords": ["post-apocalyptic", "apocalypse", "survival"]},
    "zombie":       {"genres": {"Horror": 0.8, "Action": 0.3}, "keywords": ["zombie", "undead", "apocalypse", "survival"]},
    "vampire":      {"genres": {"Horror": 0.7, "Fantasy": 0.3}, "keywords": ["vampire", "supernatural", "blood"]},
    "supernatural": {"genres": {"Horror": 0.5, "Fantasy": 0.5, "Thriller": 0.3}, "keywords": ["supernatural", "ghost", "paranormal"]},
    "magic":        {"genres": {"Fantasy": 0.8, "Adventure": 0.3}, "keywords": ["magic", "witch", "wizard", "sorcery"]},
    "time":         {"genres": {"Science Fiction": 0.6, "Drama": 0.3}, "keywords": ["time travel", "time loop", "time warp"]},
    "timetravel":   {"genres": {"Science Fiction": 0.7}, "keywords": ["time travel", "time loop", "paradox"]},
    "heist":        {"genres": {"Crime": 0.8, "Thriller": 0.5, "Action": 0.3}, "keywords": ["heist", "robbery", "theft", "caper"]},
    "spy":          {"genres": {"Action": 0.6, "Thriller": 0.7}, "keywords": ["spy", "espionage", "secret agent", "cia"]},
    "espionage":    {"genres": {"Thriller": 0.8, "Action": 0.4}, "keywords": ["espionage", "spy", "intelligence"]},
    "detective":    {"genres": {"Mystery": 0.8, "Crime": 0.6, "Thriller": 0.3}, "keywords": ["detective", "investigation", "murder mystery"]},
    "murder":       {"genres": {"Crime": 0.7, "Mystery": 0.6, "Thriller": 0.5}, "keywords": ["murder", "serial killer", "investigation"]},
    "serial":       {"genres": {"Crime": 0.6, "Thriller": 0.7}, "keywords": ["serial killer", "psychopath", "investigation"]},
    "mafia":        {"genres": {"Crime": 0.9, "Drama": 0.4}, "keywords": ["mafia", "organized crime", "gangster"]},
    "gangster":     {"genres": {"Crime": 0.9, "Drama": 0.3}, "keywords": ["gangster", "organized crime", "mafia"]},
    "samurai":      {"genres": {"Action": 0.7, "History": 0.4, "Drama": 0.3}, "keywords": ["samurai", "feudal japan", "sword fight"]},
    "martial":      {"genres": {"Action": 0.9}, "keywords": ["martial arts", "kung fu", "karate"]},
    "superhero":    {"genres": {"Action": 0.8, "Adventure": 0.5, "Science Fiction": 0.3}, "keywords": ["superhero", "dc comics", "marvel comics"]},
    "comic":        {"genres": {"Action": 0.5, "Adventure": 0.4, "Comedy": 0.3}, "keywords": ["based on comic", "superhero", "comic book"]},
    "survival":     {"genres": {"Adventure": 0.6, "Thriller": 0.5, "Drama": 0.4}, "keywords": ["survival", "wilderness", "stranded"]},
    "nature":       {"genres": {"Documentary": 0.7, "Adventure": 0.3}, "keywords": ["nature", "wildlife", "environment"]},
    "ocean":        {"genres": {"Adventure": 0.5, "Documentary": 0.4}, "keywords": ["ocean", "underwater", "deep sea", "shipwreck"]},
    "sports":       {"genres": {"Drama": 0.5}, "keywords": ["sport", "underdog", "competition", "coach"]},
    "racing":       {"genres": {"Action": 0.5, "Drama": 0.4}, "keywords": ["racing", "car", "motorsport"]},
    "music":        {"genres": {"Music": 0.8, "Drama": 0.3}, "keywords": ["music", "musician", "rock band", "concert"]},
    "biopic":       {"genres": {"Drama": 0.7, "History": 0.4}, "keywords": ["biography", "based on true story", "biopic"]},
    "true":         {"genres": {"Drama": 0.5, "Crime": 0.3}, "keywords": ["based on true story"]},
    "political":    {"genres": {"Drama": 0.5, "Thriller": 0.4}, "keywords": ["politics", "political thriller", "corruption", "government"]},
    "psychological":{"genres": {"Thriller": 0.7, "Drama": 0.5, "Horror": 0.3}, "keywords": ["psychological", "mind game", "mental illness"]},
    "mindbending":  {"genres": {"Science Fiction": 0.6, "Thriller": 0.5}, "keywords": ["twist ending", "mind-bending", "nonlinear timeline"]},
    "mind-bending": {"genres": {"Science Fiction": 0.6, "Thriller": 0.5}, "keywords": ["twist ending", "mind-bending", "nonlinear timeline"]},
    "cerebral":     {"genres": {"Science Fiction": 0.5, "Drama": 0.5, "Thriller": 0.4}, "keywords": ["philosophical", "psychological", "existential"]},
    "philosophical":{"genres": {"Drama": 0.6, "Science Fiction": 0.4}, "keywords": ["philosophical", "existential", "meaning of life"]},
    "coming-of-age":{"genres": {"Drama": 0.7, "Comedy": 0.3}, "keywords": ["coming of age", "teenager", "youth", "growing up"]},
    "comingofage":  {"genres": {"Drama": 0.7, "Comedy": 0.3}, "keywords": ["coming of age", "teenager", "youth"]},
    "teen":         {"genres": {"Drama": 0.4, "Comedy": 0.4}, "keywords": ["teenager", "high school", "coming of age"]},
    "kids":         {"genres": {"Family": 0.8, "Animation": 0.5, "Comedy": 0.3}, "keywords": ["children", "family friendly"]},
    "family-friendly": {"genres": {"Family": 0.9, "Animation": 0.4, "Comedy": 0.3}, "keywords": ["family friendly", "children"]},

    # ── Anime-specific ──
    "anime":        {"genres": {"Animation": 0.8}, "keywords": ["anime"], "domain": "anime"},
    "manga":        {"genres": {"Animation": 0.7}, "keywords": ["based on manga", "anime"], "domain": "anime"},
    "shounen":      {"genres": {"Animation": 0.6, "Action": 0.5}, "keywords": ["shounen", "anime", "based on manga"]},
    "shonen":       {"genres": {"Animation": 0.6, "Action": 0.5}, "keywords": ["shounen", "anime"]},
    "seinen":       {"genres": {"Animation": 0.5, "Drama": 0.4}, "keywords": ["seinen", "anime"]},
    "isekai":       {"genres": {"Animation": 0.6, "Fantasy": 0.5}, "keywords": ["isekai", "anime", "parallel world"]},
    "mecha":        {"genres": {"Animation": 0.6, "Science Fiction": 0.5, "Action": 0.4}, "keywords": ["mecha", "anime", "robot"]},
    "slice-of-life":{"genres": {"Animation": 0.4, "Drama": 0.4, "Comedy": 0.3}, "keywords": ["slice of life", "anime"]},
    "magical-girl": {"genres": {"Animation": 0.6, "Fantasy": 0.4}, "keywords": ["magical girl", "anime"]},
    "ecchi":        {"genres": {"Animation": 0.5, "Comedy": 0.3}, "keywords": ["ecchi", "anime", "fan service"]},
    "hentai":       {"genres": {"Animation": 0.5}, "keywords": ["hentai", "anime"]},
    "kaiju":        {"genres": {"Action": 0.6, "Science Fiction": 0.5}, "keywords": ["kaiju", "giant monster"]},
    "studio-ghibli":{"genres": {"Animation": 0.8, "Fantasy": 0.5, "Family": 0.3}, "keywords": ["anime", "studio ghibli"]},
    "ghibli":       {"genres": {"Animation": 0.8, "Fantasy": 0.5, "Family": 0.3}, "keywords": ["anime", "studio ghibli"]},

    # ── Style / Quality descriptors ──
    "classic":      {"genres": {}, "keywords": ["classic"], "era": (1920, 1985)},
    "retro":        {"genres": {}, "keywords": [], "era": (1960, 1989)},
    "80s":          {"genres": {}, "keywords": ["1980s"], "era": (1980, 1989)},
    "90s":          {"genres": {}, "keywords": ["1990s"], "era": (1990, 1999)},
    "modern":       {"genres": {}, "keywords": [], "era": (2015, 2030)},
    "new":          {"genres": {}, "keywords": [], "era": (2023, 2030)},
    "recent":       {"genres": {}, "keywords": [], "era": (2023, 2030)},
    "old":          {"genres": {}, "keywords": [], "era": (1920, 1990)},
    "short":        {"genres": {}, "keywords": [], "max_runtime": 100},
    "quick":        {"genres": {}, "keywords": [], "max_runtime": 95},
    "long":         {"genres": {}, "keywords": [], "min_runtime": 150},
    "rated":        {"genres": {}, "keywords": [], "min_rating": 7.5},
    "great":        {"genres": {}, "keywords": [], "min_rating": 7.5},
    "best":         {"genres": {}, "keywords": [], "min_rating": 8.0},
    "top":          {"genres": {}, "keywords": [], "min_rating": 8.0},
    "underrated":   {"genres": {}, "keywords": ["cult film", "independent film"], "max_rating": 7.5},
    "indie":        {"genres": {}, "keywords": ["independent film", "indie"]},
    "arthouse":     {"genres": {}, "keywords": ["arthouse", "art film", "experimental"]},
    "cult":         {"genres": {}, "keywords": ["cult film", "b-movie"]},
    "slow":         {"genres": {"Drama": 0.4}, "keywords": ["slow burn"]},
    "slowburn":     {"genres": {"Drama": 0.4, "Thriller": 0.3}, "keywords": ["slow burn", "atmospheric"]},
    "fast":         {"genres": {"Action": 0.6}, "keywords": ["fast-paced", "car chase"]},
    "loud":         {"genres": {"Action": 0.7}, "keywords": ["explosion", "destruction"]},
    "quiet":        {"genres": {"Drama": 0.5}, "keywords": ["slow burn", "contemplative", "minimalist"]},
    "beautiful":    {"genres": {}, "keywords": ["visually stunning", "cinematography"]},
    "visually":     {"genres": {}, "keywords": ["visually stunning", "cinematography"]},
    "stunning":     {"genres": {}, "keywords": ["visually stunning", "cinematography"]},

    # ── Domain hints ──
    "movie":        {"genres": {}, "keywords": [], "domain": "movies"},
    "movies":       {"genres": {}, "keywords": [], "domain": "movies"},
    "film":         {"genres": {}, "keywords": [], "domain": "movies"},
    "show":         {"genres": {}, "keywords": [], "domain": "tv"},
    "series":       {"genres": {}, "keywords": [], "domain": "tv"},
    "tv":           {"genres": {}, "keywords": [], "domain": "tv"},
}

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


# ── Preset moods (for UI quick-pick buttons) ────────────────────

MOOD_PRESETS: dict[str, str] = {
    "🚀 Sci-Fi Epic": "epic sci-fi space",
    "😱 Horror Night": "scary horror supernatural",
    "😂 Comedy": "funny comedy hilarious",
    "🎌 Anime Binge": "anime action shounen",
    "🧠 Mind-Bender": "cerebral mind-bending sci-fi",
    "💕 Date Night": "romantic comedy heartwarming not horror",
    "👊 Action Pack": "intense action badass fast",
    "🔍 Mystery": "mystery detective suspenseful",
    "🎭 Drama": "emotional drama slow burn",
    "👨‍👩‍👧 Family": "family-friendly kids animated fun",
    "🌙 Chill Evening": "relaxing chill feel-good not intense",
    "🗡️ Samurai / Martial Arts": "samurai martial arts anime",
    "🧟 Zombie Apocalypse": "zombie apocalyptic survival horror",
    "🕵️ Heist / Crime": "heist crime thriller clever",
    "🌍 True Story": "true biopic historical drama",
    "🏎️ Retro 80s": "80s action fun retro",
}
