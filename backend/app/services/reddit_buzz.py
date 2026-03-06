"""Reddit Buzz — Talk of the Web integration.

Scrapes top posts from film/TV subreddits, extracts title mentions,
and cross-references against TMDB for enriched recommendations.

Uses Reddit's public JSON API (no auth required for read-only public access).
"""

import re
import logging
import asyncio
import httpx
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

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

# Matches quoted titles: "Movie Title" or 'Movie Title' or 'Movie Title'
QUOTED_RE = re.compile(r'[\u2018\u2019\u201c\u201d\x27"\u2032\u2033]([A-Z][^\u2018\u2019\u201c\u201d\x27"\u2032\u2033\n]{2,60})[\u2018\u2019\u201c\u201d\x27"\u2032\u2033]')

# Matches "Movie Title (2024)" or "Movie Title (2025)"
YEAR_RE = re.compile(r"""([A-Z][A-Za-z0-9:&'\-,.\s]{2,50})\s*\((\d{4})\)""")

# Common noise phrases to filter out
NOISE = {"Official Trailer", "First Look", "Final Trailer", "Teaser Trailer",
         "New Trailer", "Full Trailer", "DISCUSSION", "Discussion Thread",
         "Weekly Discussion", "What I Watched", "Recommendation Thread",
         "Daily Thread", "What Are You Watching", "Mod Post"}


@dataclass
class BuzzItem:
    """A discussion item from Reddit with optional TMDB match."""
    title: str              # Reddit post title
    subreddit: str          # Source subreddit
    category: str           # movie/tv/anime/mixed
    url: str                # Reddit permalink
    score: int              # Reddit upvotes
    num_comments: int       # Comment count
    created_utc: float      # Unix timestamp
    extracted_title: str | None = None   # Extracted media title
    extracted_year: int | None = None    # Extracted year
    tmdb_id: int | None = None
    tmdb_title: str | None = None
    tmdb_type: str | None = None  # "movie" or "tv"
    poster_url: str | None = None
    vote_average: float | None = None
    overview: str | None = None


async def fetch_subreddit(sub: str, sort: str = "hot", limit: int = 25) -> list[dict]:
    """Fetch top posts from a subreddit via JSON API."""
    url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}&raw_json=1"
    headers = {"User-Agent": "Recommendarr/0.5 (media recommendation engine)"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return [p["data"] for p in posts if p.get("kind") == "t3"]
    except Exception as e:
        logger.warning(f"Reddit fetch failed for r/{sub}: {e}")
        return []


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

    # Strategy 1: Year pattern — "Movie Title (2024)"
    m = YEAR_RE.search(post_title)
    if m:
        title = m.group(1).strip()
        year = int(m.group(2))
        if title not in NOISE and len(title) > 2:
            return title, year

    # Strategy 2: Quoted titles (straight and curly quotes)
    m = QUOTED_RE.search(post_title)
    if m:
        title = m.group(1).strip()
        if title not in NOISE and len(title) > 2:
            return title, None

    # Strategy 3: Pre-separator extraction
    # "Alien: Earth - New trailer released" → "Alien: Earth"
    # "The Boys | Final Season Trailer" → "The Boys"
    separators = [" - ", " | ", " — ", " – "]
    for sep in separators:
        if sep in post_title:
            candidate = post_title.split(sep)[0].strip()
            # Only use if it looks like a title (starts with uppercase, reasonable length)
            if 2 < len(candidate) < 60 and candidate[0].isupper() and candidate not in NOISE:
                # Extract year from the rest if present
                rest = post_title.split(sep, 1)[1]
                yr_m = re.search(r"\((\d{4})\)", rest)
                yr = int(yr_m.group(1)) if yr_m else None
                return candidate, yr

    # Strategy 4: Trim noise suffixes and try
    # "Jujutsu Kaisen new movie announced" → "Jujutsu Kaisen"
    noise_suffixes = ["official trailer", "new trailer", "trailer", "teaser",
                      "first look", "review", "discussion", "new season",
                      "season \\d+", "announced", "confirmed", "renewed",
                      "cancelled", "canceled", "poster", "key visual",
                      "premium version"]
    cleaned = post_title.strip()
    for suffix in noise_suffixes:
        pattern = re.compile(r"[\s•\-|:]+(?:" + suffix + r").*$", re.IGNORECASE)
        cleaned = pattern.sub("", cleaned).strip()

    # If cleaning removed something meaningful and left a reasonable title
    if cleaned != post_title.strip() and 2 < len(cleaned) < 60 and cleaned[0].isupper():
        return cleaned, None

    return None, None


async def search_tmdb(seerr_client, title: str, year: int | None = None,
                      media_type: str | None = None) -> dict | None:
    """Search TMDB via Seerr for a media title."""
    try:
        # Clean title for Seerr search (colons and special chars cause 400 errors)
        clean = re.sub(r'[:\?\!\(\)\[\]]+', ' ', title).strip()
        clean = re.sub(r'\s+', ' ', clean)  # collapse whitespace
        results = await seerr_client.search(clean, page=1)
        if not results:
            return None

        def _fmt(r):
            poster = getattr(r, "poster_path", None)
            return {
                "tmdb_id": r.tmdb_id,
                "title": getattr(r, "title", "") or "",
                "type": getattr(r, "media_type", ""),
                "poster_url": f"https://image.tmdb.org/t/p/w342{poster}" if poster else None,
                "vote_average": getattr(r, "vote_average", 0),
                "overview": (getattr(r, "overview", "") or "")[:200],
            }

        for r in results[:5]:
            rtype = getattr(r, "media_type", "")
            # If we have a year, try to match it
            if year:
                ryear = getattr(r, "year", None)
                if ryear and ryear != year:
                    continue
            # If we have a media type hint, try to match
            if media_type == "movie" and rtype != "movie":
                continue
            if media_type == "tv" and rtype not in ("tv", "show"):
                continue
            return _fmt(r)

        # Fallback: return first result
        return _fmt(results[0])
    except Exception as e:
        logger.warning(f"TMDB search failed for \'{title}\': {e}")
        return None


async def get_reddit_buzz(seerr_client, subreddits: list[str] | None = None,
                          limit_per_sub: int = 15,
                          enrich_tmdb: bool = True) -> list[dict]:
    """Fetch and process Reddit buzz from film/TV subreddits.

    Args:
        seerr_client: SeerrClient for TMDB lookups
        subreddits: Optional list of subreddit names to fetch. Defaults to all SOURCES.
        limit_per_sub: Posts per subreddit
        enrich_tmdb: Whether to cross-reference with TMDB

    Returns:
        List of buzz items sorted by Reddit score, with optional TMDB enrichment.
    """
    sources = SOURCES
    if subreddits:
        sources = [s for s in SOURCES if s["sub"].lower() in [x.lower() for x in subreddits]]
        if not sources:
            sources = [{"sub": s, "label": f"r/{s}", "category": "mixed"} for s in subreddits]

    # Fetch all subreddits concurrently
    tasks = [fetch_subreddit(s["sub"], limit=limit_per_sub) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[BuzzItem] = []
    seen_titles = set()

    for source, posts in zip(sources, results):
        if isinstance(posts, Exception):
            logger.warning(f"Skipping r/{source['sub']}: {posts}")
            continue

        for post in posts:
            if post.get("stickied") or post.get("distinguished"):
                continue

            title = post.get("title", "")
            extracted, year = extract_media_title(title)

            item = BuzzItem(
                title=title,
                subreddit=source["sub"],
                category=source["category"],
                url=f"https://reddit.com{post.get('permalink', '')}",
                score=post.get("score", 0),
                num_comments=post.get("num_comments", 0),
                created_utc=post.get("created_utc", 0),
                extracted_title=extracted,
                extracted_year=year,
            )
            all_items.append(item)

            if extracted:
                seen_titles.add(extracted.lower())

    # Sort by Reddit score
    all_items.sort(key=lambda x: x.score, reverse=True)

    # TMDB enrichment for items with extracted titles
    if enrich_tmdb and seerr_client:
        enriched = set()
        enrich_tasks = []

        for item in all_items:
            if item.extracted_title and item.extracted_title.lower() not in enriched:
                enriched.add(item.extracted_title.lower())
                # Don't filter by media_type — subreddit categories are rough approximations
                # (r/movies discusses TV shows too, r/television discusses movies)
                enrich_tasks.append((item, search_tmdb(seerr_client, item.extracted_title, item.extracted_year, None)))

        logger.info(f"[BUZZ] Enriching {len(enrich_tasks)} unique titles via TMDB")

        if enrich_tasks:
            # Rate-limit TMDB searches to avoid overwhelming Seerr (400 errors)
            sem = asyncio.Semaphore(3)
            async def _limited(coro):
                async with sem:
                    await asyncio.sleep(0.15)  # small stagger
                    return await coro
            tmdb_results = await asyncio.gather(*[_limited(t[1]) for t in enrich_tasks], return_exceptions=True)
            title_tmdb_map = {}

            for (item, _), result in zip(enrich_tasks, tmdb_results):
                if isinstance(result, Exception):
                    logger.warning(f"[BUZZ] TMDB exception for '{item.extracted_title}': {result}")
                    continue
                if result:
                    title_tmdb_map[item.extracted_title.lower()] = result
                    logger.info(f"[BUZZ] MATCHED: '{item.extracted_title}' → {result.get('title')} (tmdb:{result.get('tmdb_id')})")
                else:
                    logger.info(f"[BUZZ] NO MATCH: '{item.extracted_title}' → None")

            logger.info(f"[BUZZ] {len(title_tmdb_map)} titles matched in TMDB")

            # Apply TMDB data to all matching items
            for item in all_items:
                if item.extracted_title and item.extracted_title.lower() in title_tmdb_map:
                    tmdb = title_tmdb_map[item.extracted_title.lower()]
                    item.tmdb_id = tmdb["tmdb_id"]
                    item.tmdb_title = tmdb["title"]
                    item.tmdb_type = tmdb["type"]
                    item.poster_url = tmdb["poster_url"]
                    item.vote_average = tmdb["vote_average"]
                    item.overview = tmdb["overview"]

    # Format output
    output = []
    for item in all_items[:60]:
        entry = {
            "reddit_title": item.title,
            "subreddit": item.subreddit,
            "category": item.category,
            "reddit_url": item.url,
            "reddit_score": item.score,
            "num_comments": item.num_comments,
            "created_utc": item.created_utc,
        }
        if item.tmdb_id:
            entry.update({
                "tmdb_id": item.tmdb_id,
                "title": item.tmdb_title,
                "media_type": item.tmdb_type,
                "poster_url": item.poster_url,
                "vote_average": item.vote_average,
                "overview": item.overview,
                "has_tmdb": True,
            })
        else:
            entry["has_tmdb"] = False
            entry["title"] = item.extracted_title or item.title

        output.append(entry)

    return output
