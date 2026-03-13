"""Cultural Pulse — RSS → LLM → themed recommendation mappings.

Fetches configured RSS sources, extracts cultural themes via LLM,
maps themes to genres/keywords/TMDB IDs, stores as ZeitgeistEvents.
Falls back to keyword extraction when AI is disabled.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_

from app.database import get_db
from app.models import PulseSource, ZeitgeistEvent, ZeitgeistMapping
from app.services.ai_client import llm_complete
from app.services.ai_config import get_ai_config
from app.services.rss_parser import fetch_rss

logger = logging.getLogger(__name__)

# Default sources seeded on first run
DEFAULT_SOURCES = [
    {"source_type": "rss", "source_name": "IndieWire", "source_url": "https://www.indiewire.com/feed/", "category": "film_news"},
    {"source_type": "rss", "source_name": "The Playlist", "source_url": "https://theplaylist.net/feed/", "category": "film_news"},
    {"source_type": "rss", "source_name": "Collider", "source_url": "https://collider.com/feed/", "category": "film_news"},
    {"source_type": "rss", "source_name": "Deadline - Film", "source_url": "https://deadline.com/v/film/feed/", "category": "film_news"},
    {"source_type": "rss", "source_name": "Screen Rant", "source_url": "https://screenrant.com/feed/", "category": "film_news"},
]

EXTRACT_SYSTEM = """You analyze entertainment news headlines to identify cultural themes and trending topics relevant to movie/TV recommendations.

From the provided headlines, extract 3-8 distinct cultural themes or trends. Each theme should be a concept that could drive recommendations.

Respond ONLY with a JSON array of objects:
[
  {
    "title": "Short theme name (2-6 words)",
    "description": "One sentence explaining the cultural moment",
    "event_type": "trend|release|award|anniversary|cultural_moment|controversy",
    "genres": ["Genre1", "Genre2"],
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "tmdb_search_queries": ["search query for TMDB"],
    "priority": "high|normal|low",
    "expires_days": 7
  }
]

Theme types:
- trend: ongoing cultural conversation (e.g., "AI in film", "nostalgia remakes")
- release: major new release driving conversation
- award: award season buzz
- anniversary: notable anniversaries of classic films
- cultural_moment: real-world event affecting viewing
- controversy: industry controversy driving interest

Valid TMDB genres: Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Mystery, Romance, Science Fiction, Thriller, War, Western.

Focus on themes that map well to recommendations. Skip generic industry business news."""


async def extract_themes_ai(headlines: list[dict]) -> list[dict]:
    """Use LLM to extract cultural themes from RSS headlines."""
    cfg = get_ai_config()
    if not cfg.is_llm_enabled:
        return extract_themes_keyword(headlines)

    text = "\n".join(
        f"- {h['title']}" + (f": {h['description'][:100]}" if h.get('description') else "")
        for h in headlines[:40]
    )

    try:
        raw = await llm_complete(
            prompt=f"Analyze these recent entertainment headlines and extract cultural themes:\n\n{text}",
            system=EXTRACT_SYSTEM,
            config=cfg,
        )
        if not raw:
            return extract_themes_keyword(headlines)
        return _parse_themes_response(raw)
    except Exception as e:
        logger.error(f"Cultural pulse LLM extraction failed: {e}")
        return extract_themes_keyword(headlines)


def _parse_themes_response(raw: str) -> list[dict]:
    """Parse LLM JSON response into theme dicts."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
        if not isinstance(data, list):
            return []
        return [t for t in data if isinstance(t, dict) and "title" in t][:8]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Cultural pulse: JSON parse failed: {e}")
        return []


def extract_themes_keyword(headlines: list[dict]) -> list[dict]:
    """Fallback: extract themes from headline keywords (no LLM)."""
    genre_hits: dict[str, int] = {}
    genre_map = {
        "horror": "Horror", "thriller": "Thriller", "comedy": "Comedy",
        "drama": "Drama", "action": "Action", "sci-fi": "Science Fiction",
        "romance": "Romance", "animated": "Animation", "anime": "Animation",
        "documentary": "Documentary", "war": "War", "fantasy": "Fantasy",
        "mystery": "Mystery", "western": "Western", "musical": "Music",
    }
    stop_words = {"this", "that", "with", "from", "about", "been", "have", "will",
                  "just", "more", "than", "also", "into", "over", "what", "when",
                  "film", "movie", "show", "series", "season", "first", "look",
                  "best", "like", "time", "year", "years"}

    for h in headlines:
        words = re.findall(r'\b[a-z]{4,}\b', (h["title"] + " " + h.get("description", "")).lower())
        for w in set(words):
            if w in genre_map:
                genre_hits[genre_map[w]] = genre_hits.get(genre_map[w], 0) + 1

    themes = []
    top_genres = sorted(genre_hits.items(), key=lambda x: x[1], reverse=True)[:3]
    for genre, count in top_genres:
        if count >= 2:
            themes.append({
                "title": f"Trending: {genre}",
                "description": f"{genre} is trending in entertainment news right now",
                "event_type": "trend", "genres": [genre], "keywords": [],
                "tmdb_search_queries": [], "priority": "normal", "expires_days": 7,
            })
    return themes[:5]


async def refresh_pulse() -> list[dict]:
    """Full pulse refresh cycle: fetch sources → extract themes → persist."""
    now = datetime.now(timezone.utc)
    sources = _get_enabled_sources()

    if not sources:
        _seed_default_sources()
        sources = _get_enabled_sources()

    all_headlines = []
    for src in sources:
        if src.last_checked_at and (now - src.last_checked_at).total_seconds() < src.check_interval_hours * 3600:
            continue
        headlines = await fetch_rss(src.source_url)
        all_headlines.extend(headlines)
        _update_source_checked(src.id, now)
        logger.info(f"Pulse: fetched {len(headlines)} from {src.source_name}")

    if not all_headlines:
        logger.info("Pulse: no new headlines to process")
        return []

    themes = await extract_themes_ai(all_headlines)
    logger.info(f"Pulse: extracted {len(themes)} themes from {len(all_headlines)} headlines")

    created = []
    for theme in themes:
        event = _create_event(theme, now)
        if event:
            created.append(event)
    return created


def get_active_events(limit: int = 10) -> list[dict]:
    """Get currently active pulse events with their mappings."""
    now = datetime.now(timezone.utc)
    with get_db() as db:
        events = db.execute(
            select(ZeitgeistEvent)
            .where(and_(ZeitgeistEvent.is_active == True, ZeitgeistEvent.expires_at > now))
            .order_by(ZeitgeistEvent.created_at.desc())
            .limit(limit)
        ).scalars().all()

        results = []
        for e in events:
            mapping = db.execute(
                select(ZeitgeistMapping).where(ZeitgeistMapping.event_id == e.id)
            ).scalar_one_or_none()
            results.append({
                "id": e.id, "title": e.title, "description": e.description,
                "event_type": e.event_type, "source_url": e.source_url,
                "source_feed": e.source_feed, "priority": e.priority,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
                "mapping": {
                    "genres": mapping.mapped_genres or [],
                    "keywords": mapping.mapped_keywords or [],
                    "themes": mapping.mapped_themes or [],
                    "tmdb_ids": mapping.mapped_tmdb_ids or [],
                    "search_query": mapping.embedding_query or "",
                } if mapping else None,
            })
        return results


def get_all_sources() -> list[dict]:
    """Get all configured pulse sources."""
    with get_db() as db:
        sources = db.execute(select(PulseSource).order_by(PulseSource.created_at)).scalars().all()
        return [{
            "id": s.id, "source_type": s.source_type, "source_name": s.source_name,
            "source_url": s.source_url, "category": s.category,
            "is_enabled": s.is_enabled, "check_interval_hours": s.check_interval_hours,
            "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
        } for s in sources]


# ── DB helpers ───────────────────────────────────────────────────

def _get_enabled_sources() -> list:
    with get_db() as db:
        return db.execute(select(PulseSource).where(PulseSource.is_enabled == True)).scalars().all()


def _seed_default_sources():
    with get_db() as db:
        for src in DEFAULT_SOURCES:
            existing = db.execute(
                select(PulseSource).where(PulseSource.source_url == src["source_url"])
            ).scalar_one_or_none()
            if not existing:
                db.add(PulseSource(**src))
        db.commit()
    logger.info(f"Pulse: seeded {len(DEFAULT_SOURCES)} default RSS sources")


def _update_source_checked(source_id: int, when: datetime):
    with get_db() as db:
        src = db.get(PulseSource, source_id)
        if src:
            src.last_checked_at = when
            db.commit()


def _create_event(theme: dict, now: datetime) -> Optional[dict]:
    """Create a ZeitgeistEvent + ZeitgeistMapping from a theme dict."""
    expires_days = int(theme.get("expires_days", 7))
    cfg = get_ai_config()

    with get_db() as db:
        existing = db.execute(
            select(ZeitgeistEvent).where(
                and_(ZeitgeistEvent.title == theme["title"], ZeitgeistEvent.is_active == True)
            )
        ).scalar_one_or_none()
        if existing:
            return None

        event = ZeitgeistEvent(
            event_type=theme.get("event_type", "trend"),
            title=theme["title"],
            description=theme.get("description", ""),
            source_feed="cultural_pulse",
            is_active=True,
            priority=theme.get("priority", "normal"),
            created_at=now,
            expires_at=now + timedelta(days=expires_days),
        )
        db.add(event)
        db.flush()

        mapping = ZeitgeistMapping(
            event_id=event.id,
            mapped_genres=theme.get("genres", []),
            mapped_keywords=theme.get("keywords", []),
            mapped_themes=theme.get("keywords", []),
            mapped_tmdb_ids=[],
            embedding_query=" ".join(theme.get("tmdb_search_queries", [])),
            weight_boost=0.15 if theme.get("priority") == "high" else 0.10,
            llm_model=cfg.llm.model if cfg.is_llm_enabled else "keyword_fallback",
            generated_at=now,
        )
        db.add(mapping)
        db.commit()
        return {"id": event.id, "title": event.title, "event_type": event.event_type}
