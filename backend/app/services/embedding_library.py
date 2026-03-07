"""Library embedding pipeline — batch embed TMDB items into ChromaDB.

Heavy lifting function split from EmbeddingService for §7.7.
"""

import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TmdbCache

logger = logging.getLogger(__name__)


async def embed_library(
    service,  # EmbeddingService instance
    db: AsyncSession,
    media_type: str = "movie",
    batch_size: int = 20,
    progress_callback=None,
) -> dict:
    """Embed all cached TMDB items that don't have embeddings yet.

    Reads from tmdb_cache, generates embeddings, stores in ChromaDB,
    updates embedding_id back in tmdb_cache.

    Returns:
        {"embedded": N, "skipped": N, "failed": N, "total": N}
    """
    from app.services.tmdb_sync import TmdbSyncService

    # Get all items needing embedding
    result = await db.execute(
        select(TmdbCache).where(
            and_(
                TmdbCache.media_type == media_type,
                TmdbCache.embedding_id.is_(None),
            )
        )
    )
    items = list(result.scalars().all())
    total = len(items)

    if total == 0:
        all_result = await db.execute(
            select(TmdbCache).where(TmdbCache.media_type == media_type)
        )
        all_count = len(list(all_result.scalars().all()))
        return {"embedded": 0, "skipped": all_count, "failed": 0, "total": all_count}

    embedded = 0
    failed = 0
    sync = TmdbSyncService.__new__(TmdbSyncService)

    for batch_start in range(0, total, batch_size):
        batch = items[batch_start:batch_start + batch_size]

        texts = []
        valid_items = []
        for item in batch:
            text = sync.build_embedding_text(item)
            if text.strip():
                texts.append(text)
                valid_items.append(item)
            else:
                failed += 1

        if not texts:
            continue

        try:
            embeddings = await service.generate_embeddings_batch(texts)
        except Exception as e:
            logger.error(f"Embedding batch failed: {e}")
            failed += len(valid_items)
            continue

        if len(embeddings) != len(valid_items):
            logger.error(f"Embedding count mismatch: {len(embeddings)} vs {len(valid_items)}")
            failed += len(valid_items)
            continue

        ids = []
        metadatas = []
        for item in valid_items:
            doc_id = f"{item.media_type}:{item.tmdb_id}"
            ids.append(doc_id)
            metadatas.append({
                "tmdb_id": item.tmdb_id,
                "media_type": item.media_type,
                "title": item.title or "",
                "year": item.year or 0,
                "vote_average": float(item.vote_average) if item.vote_average else 0.0,
                "popularity": float(item.popularity) if item.popularity else 0.0,
                "original_language": item.original_language or "en",
            })

        try:
            await service.upsert_embeddings(ids, embeddings, texts, metadatas)
            for item, doc_id in zip(valid_items, ids):
                item.embedding_id = doc_id
            await db.commit()
            embedded += len(valid_items)
        except Exception as e:
            logger.error(f"ChromaDB upsert failed: {e}")
            failed += len(valid_items)
            await db.rollback()

        if progress_callback:
            await progress_callback(
                batch_start + len(batch), total,
                valid_items[-1].title if valid_items else "?"
            )

    return {
        "embedded": embedded,
        "skipped": total - embedded - failed,
        "failed": failed,
        "total": total,
    }
