"""Reddit Buzz — Talk of the Web integration.

Scrapes top posts from film/TV subreddits, extracts title mentions,
and cross-references against TMDB for enriched recommendations.
"""

import logging
import asyncio
import httpx
from datetime import datetime, timezone

from app.services.reddit_buzz_parser import (
    SOURCES, BuzzItem, extract_media_title,
)

logger = logging.getLogger(__name__)


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
