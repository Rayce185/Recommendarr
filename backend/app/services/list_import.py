"""List Import Engine — extract media titles from URLs or pasted text via LLM.

Flow: text/URL → LLM extraction → TMDB resolution → actionable results.
Falls back to regex-based extraction when AI is disabled.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.services.ai_client import llm_complete
from app.services.ai_config import get_ai_config

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = """You extract movie and TV show titles from text. The text may be:
- A list article ("Top 10 sci-fi movies of 2024")
- A forum post or Reddit thread discussing recommendations
- A Letterboxd list or watchlist export
- A casual conversation mentioning titles
- Any text with embedded media references

Respond ONLY with a JSON array of objects. Each object:
{
  "title": "exact title as commonly known",
  "year": 2024,        // null if unknown
  "type": "movie",     // "movie" or "tv", null if ambiguous
  "confidence": 0.9    // 0.0-1.0, how sure you are this is a real title
}

Rules:
- Extract ONLY movie/TV titles, not books, games, or music
- Use the most common English title (e.g. "Spirited Away" not "Sen to Chihiro no Kamikakushi")
- If a title appears multiple times, include it only once
- Include year only if clearly stated or you're confident
- Set confidence low (<0.5) for ambiguous mentions
- Maximum 50 titles per extraction
- Do NOT invent titles — only extract what's in the text"""

# Simple regex patterns for fallback extraction (no LLM)
TITLE_PATTERNS = [
    # "Title (Year)" pattern
    re.compile(r'(?:^|\n)\s*(?:\d+[\.\)]\s*)?["\u201c]?([A-Z][^"\u201d\n]{2,60}?)["\u201d]?\s*\((\d{4})\)', re.MULTILINE),
    # Numbered list: "1. Title"
    re.compile(r'(?:^|\n)\s*\d+[\.\)]\s+([A-Z][^\n]{2,60})(?:\s*[-\u2013]\s|\s*\(|\s*$)', re.MULTILINE),
    # Markdown bold: "**Title**"
    re.compile(r'\*\*([A-Z][^*]{2,60})\*\*'),
]


@dataclass
class ExtractedTitle:
    title: str
    year: Optional[int] = None
    media_type: Optional[str] = None  # "movie" or "tv"
    confidence: float = 0.5


@dataclass
class ResolvedTitle:
    """An extracted title matched against TMDB."""
    extracted: ExtractedTitle
    tmdb_id: Optional[int] = None
    tmdb_title: Optional[str] = None
    tmdb_type: Optional[str] = None
    tmdb_year: Optional[int] = None
    poster_url: Optional[str] = None
    vote_average: float = 0.0
    overview: str = ""
    in_library: bool = False
    matched: bool = False


async def fetch_url_text(url: str) -> str:
    """Fetch a URL and extract readable text content."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Recommendarr/1.0)",
        "Accept": "text/html,application/xhtml+xml,text/plain",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content = resp.text

    # Strip HTML tags for a rough text extraction
    # (good enough for LLM — it handles messy text well)
    text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)  # HTML entities
    text = re.sub(r'\s+', ' ', text).strip()

    # Truncate to ~8000 chars to keep prompt reasonable
    if len(text) > 8000:
        text = text[:8000] + "..."

    return text


async def extract_titles_ai(text: str) -> list[ExtractedTitle]:
    """Use LLM to extract titles from text."""
    cfg = get_ai_config()
    if not cfg.is_llm_enabled:
        return extract_titles_regex(text)

    try:
        raw = await llm_complete(
            prompt=f"Extract all movie and TV show titles from this text:\n\n{text[:6000]}",
            system=EXTRACT_SYSTEM,
            config=cfg,
        )
        if not raw:
            logger.warning("List import: empty LLM response, falling back to regex")
            return extract_titles_regex(text)

        return _parse_extraction(raw)
    except Exception as e:
        logger.error(f"List import LLM extraction failed: {e}")
        return extract_titles_regex(text)


def _parse_extraction(raw: str) -> list[ExtractedTitle]:
    """Parse LLM JSON response into ExtractedTitle list."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON array in response
        match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            logger.warning("List import: could not parse LLM response as JSON")
            return []

    if not isinstance(data, list):
        return []

    results = []
    seen = set()
    for item in data[:50]:
        if not isinstance(item, dict) or "title" not in item:
            continue
        title = str(item["title"]).strip()
        key = title.lower()
        if key in seen or len(title) < 2:
            continue
        seen.add(key)

        results.append(ExtractedTitle(
            title=title,
            year=int(item["year"]) if item.get("year") else None,
            media_type=item.get("type") if item.get("type") in ("movie", "tv") else None,
            confidence=min(1.0, float(item.get("confidence", 0.5))),
        ))

    return results


def extract_titles_regex(text: str) -> list[ExtractedTitle]:
    """Fallback: regex-based title extraction for when AI is disabled."""
    results = []
    seen = set()

    for pattern in TITLE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            title = groups[0].strip().rstrip(".,;:-")
            year = int(groups[1]) if len(groups) > 1 and groups[1] else None
            key = title.lower()
            if key in seen or len(title) < 3 or len(title) > 80:
                continue
            seen.add(key)
            results.append(ExtractedTitle(
                title=title, year=year, confidence=0.4,
            ))

    return results[:50]


async def resolve_titles(titles: list[ExtractedTitle], seerr_client) -> list[ResolvedTitle]:
    """Resolve extracted titles against TMDB via Seerr search."""
    results = []

    for ext in titles:
        resolved = ResolvedTitle(extracted=ext)
        try:
            # Build search query
            query = re.sub(r'[:\?\!\(\)\[\]]+', ' ', ext.title).strip()
            query = re.sub(r'\s+', ' ', query)

            search_results = await seerr_client.search(query, page=1)
            if not search_results:
                results.append(resolved)
                continue

            # Find best match
            best = None
            for r in search_results[:8]:
                rtype = getattr(r, "media_type", "")
                ryear = getattr(r, "year", None)

                # Type filter
                if ext.media_type == "movie" and rtype != "movie":
                    continue
                if ext.media_type == "tv" and rtype not in ("tv", "show"):
                    continue

                # Year match bonus
                if ext.year and ryear and abs(ext.year - ryear) > 1:
                    continue

                best = r
                break

            if not best and search_results:
                best = search_results[0]

            if best:
                poster = getattr(best, "poster_path", None)
                resolved.tmdb_id = best.tmdb_id
                resolved.tmdb_title = getattr(best, "title", "") or ""
                resolved.tmdb_type = getattr(best, "media_type", "")
                resolved.tmdb_year = getattr(best, "year", None)
                resolved.poster_url = f"https://image.tmdb.org/t/p/w185{poster}" if poster else None
                resolved.vote_average = getattr(best, "vote_average", 0) or 0
                resolved.overview = (getattr(best, "overview", "") or "")[:200]
                resolved.matched = True

        except Exception as e:
            logger.warning(f"TMDB resolve failed for '{ext.title}': {e}")

        results.append(resolved)

    return results
