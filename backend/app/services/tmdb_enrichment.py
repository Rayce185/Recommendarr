"""Background TMDB enrichment — fills TmdbCache for all library items.

Runs as a low-priority background task after startup warmup.
Finds library items without TmdbCache entries and fetches their
metadata from TMDB, rate-limited to stay under API limits.
"""

import asyncio
import logging
import time

from app.database import get_db
from app.models import TmdbCache
from app.services.cache import get_cache
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Conservative rate: ~15 req/s (TMDB allows 40)
RATE_DELAY = 0.07
BATCH_LOG_INTERVAL = 50


async def run_tmdb_enrichment():
    """Enrich all library items that are missing from TmdbCache.

    Called once after startup warmup. Fetches TMDB detail for each
    missing item, which auto-caches via TMDBClient.get_detail().
    """
    await asyncio.sleep(30)  # Let warmup finish first

    from app.services.factory import get_stack
    stack = get_stack()
    if not stack.tmdb:
        logger.info("TMDB enrichment skipped — no TMDB client configured")
        return

    cache = get_cache()
    candidates = cache.get_library("all")
    if not candidates:
        logger.info("TMDB enrichment skipped — no library candidates cached yet")
        return

    # Find items NOT in TmdbCache
    all_items = [(c["tmdb_id"], c.get("media_type", "movie")) for c in candidates if c.get("tmdb_id")]

    with get_db() as db:
        cached_ids = set(
            db.execute(select(TmdbCache.tmdb_id)).scalars().all()
        )

    missing = [(tid, mt) for tid, mt in all_items if tid not in cached_ids]
    if not missing:
        logger.info(f"TMDB enrichment: all {len(all_items)} library items already cached")
        return

    logger.info(f"TMDB enrichment starting: {len(missing)}/{len(all_items)} items need fetching")
    start = time.monotonic()
    fetched = 0
    failed = 0

    for i, (tmdb_id, media_type) in enumerate(missing):
        try:
            await stack.tmdb.get_detail(tmdb_id, media_type)
            fetched += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.debug(f"TMDB enrichment: failed tmdb_id={tmdb_id}: {e}")
        await asyncio.sleep(RATE_DELAY)
        if (i + 1) % BATCH_LOG_INTERVAL == 0:
            elapsed = time.monotonic() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(missing) - i - 1) / rate if rate > 0 else 0
            logger.info(f"TMDB enrichment progress: {i+1}/{len(missing)} "
                        f"({fetched} ok, {failed} err, ~{remaining:.0f}s remaining)")

    elapsed = time.monotonic() - start
    logger.info(f"TMDB enrichment complete: {fetched} fetched, {failed} failed "
                f"in {elapsed:.1f}s ({len(all_items)} total library items)")

    # Re-enrich library candidates now that we have more cache data
    if fetched > 0:
        from app.services.rec_library import enrich_candidates_from_cache
        candidates = cache.get_library("all")
        if candidates:
            enrich_candidates_from_cache(candidates)
            cache.set_library("all", candidates)
            logger.info(f"Library candidates re-enriched after TMDB backfill")
