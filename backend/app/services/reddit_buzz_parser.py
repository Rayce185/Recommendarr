"""Reddit Buzz parser — title extraction and data models.

Contains the regex-heavy title extraction logic, constants,
and BuzzItem dataclass. Split from reddit_buzz.py for §7.7.
"""

import re
from dataclasses import dataclass


# ── Subreddit sources ────────────────────────────────────────────

SOURCES = [
    {"sub": "movies",       "label": "r/movies",       "category": "movie"},
    {"sub": "television",   "label": "r/television",   "category": "tv"},
    {"sub": "anime",        "label": "r/anime",        "category": "anime"},
    {"sub": "MovieSuggestions", "label": "r/MovieSuggestions", "category": "movie"},
    {"sub": "horror",       "label": "r/horror",       "category": "movie"},
    {"sub": "scifi",        "label": "r/scifi",        "category": "mixed"},
    {"sub": "kdrama",       "label": "r/kdrama",       "category": "tv"},
    {"sub": "Documentaries","label": "r/Documentaries", "category": "mixed"},
]

# ── Title extraction patterns ────────────────────────────────────

QUOTED_RE = re.compile(r'[\u2018\u2019\u201c\u201d\x27"\u2032\u2033]([A-Z][^\u2018\u2019\u201c\u201d\x27"\u2032\u2033\n]{2,60})[\u2018\u2019\u201c\u201d\x27"\u2032\u2033]')
YEAR_RE = re.compile(r"""([A-Z][A-Za-z0-9:&'\-,.\s]{2,50})\s*\((\d{4})\)""")
NOISE = {"Official Trailer", "First Look", "Final Trailer", "Teaser Trailer",
         "New Trailer", "Full Trailer", "DISCUSSION", "Discussion Thread",
         "Weekly Discussion", "What I Watched", "Recommendation Thread",
         "Daily Thread", "What Are You Watching", "Mod Post"}


@dataclass
class BuzzItem:
    """A discussion item from Reddit with optional TMDB match."""
    title: str
    subreddit: str
    category: str
    url: str
    score: int
    num_comments: int
    created_utc: float
    extracted_title: str | None = None
    extracted_year: int | None = None
    tmdb_id: int | None = None
    tmdb_title: str | None = None
    tmdb_type: str | None = None
    poster_url: str | None = None
    vote_average: float | None = None
    overview: str | None = None


def extract_media_title(post_title: str) -> tuple[str | None, int | None]:
    """Try to extract a movie/show title from a Reddit post title.

    Uses multiple strategies in priority order:
    1. Year pattern: "Movie Title (2024)"
    2. Quoted titles: "Movie Title" or 'Movie Title'
    3. Pre-separator: text before common separators (-, |, :, —)
    4. Full title cleanup: strip noise words and try the whole thing

    Returns (title, year) or (None, None) if no title found.
    """
    lower = post_title.lower()
    if any(n.lower() in lower for n in ["weekly", "daily thread", "mod post", "megathread",
                                         "what are you watching", "recommendation thread"]):
        return None, None

    # Strategy 1: Year pattern
    m = YEAR_RE.search(post_title)
    if m:
        title = m.group(1).strip()
        year = int(m.group(2))
        if title not in NOISE and len(title) > 2:
            return title, year

    # Strategy 2: Quoted titles
    m = QUOTED_RE.search(post_title)
    if m:
        title = m.group(1).strip()
        if title not in NOISE and len(title) > 2:
            return title, None

    # Strategy 3: Pre-separator extraction
    separators = [" - ", " | ", " — ", " – "]
    for sep in separators:
        if sep in post_title:
            candidate = post_title.split(sep)[0].strip()
            if 2 < len(candidate) < 60 and candidate[0].isupper() and candidate not in NOISE:
                rest = post_title.split(sep, 1)[1]
                yr_m = re.search(r"\((\d{4})\)", rest)
                yr = int(yr_m.group(1)) if yr_m else None
                return candidate, yr

    # Strategy 4: Trim noise suffixes
    noise_suffixes = ["official trailer", "new trailer", "trailer", "teaser",
                      "first look", "review", "discussion", "new season",
                      "season \\d+", "announced", "confirmed", "renewed",
                      "cancelled", "canceled", "poster", "key visual",
                      "premium version"]
    cleaned = post_title.strip()
    for suffix in noise_suffixes:
        pattern = re.compile(r"[\s•\-|:]+(?:" + suffix + r").*$", re.IGNORECASE)
        cleaned = pattern.sub("", cleaned).strip()

    if cleaned != post_title.strip() and 2 < len(cleaned) < 60 and cleaned[0].isupper():
        return cleaned, None

    return None, None
