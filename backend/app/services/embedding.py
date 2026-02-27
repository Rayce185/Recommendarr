"""Embedding pipeline service.

Generates vector embeddings from TMDB metadata text using Ollama,
stores them in ChromaDB for semantic similarity search.
"""

import httpx
import logging
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import TmdbCache

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates and manages content embeddings in ChromaDB."""

    def __init__(
        self,
        ollama_url: str,
        chromadb_url: str,
        collection_name: str = "recommendarr",
        model: str = "nomic-embed-text",
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.chromadb_url = chromadb_url.rstrip("/")
        self.collection_name = collection_name
        self.model = model
        self._collection_id: Optional[str] = None

    # ── ChromaDB collection management ───────────────────────────

    async def ensure_collection(self) -> str:
        """Get or create the ChromaDB collection. Returns collection ID.

        Uses ChromaDB v2 API: /api/v2/tenants/default_tenant/databases/default_database/collections
        """
        if self._collection_id:
            return self._collection_id

        v2_base = f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database"

        async with httpx.AsyncClient(timeout=10.0) as client:
            # List existing collections
            try:
                resp = await client.get(f"{v2_base}/collections")
                if resp.status_code == 200:
                    collections = resp.json()
                    for c in collections:
                        if c.get("name") == self.collection_name:
                            self._collection_id = c["id"]
                            return self._collection_id
            except Exception:
                pass

            # Create new collection with cosine distance
            resp = await client.post(
                f"{v2_base}/collections",
                json={
                    "name": self.collection_name,
                    "configuration": {
                        "hnsw": {"space": "cosine"},
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._collection_id = data["id"]
            return self._collection_id

    # ── Embedding generation ─────────────────────────────────────

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a single embedding vector via Ollama."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.ollama_url}/api/embed",
                json={"model": self.model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama /api/embed returns {"embeddings": [[...], ...]}
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
            raise ValueError(f"No embedding returned for text: {text[:50]}...")

    async def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in one call."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.ollama_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("embeddings", [])

    # ── ChromaDB operations ──────────────────────────────────────

    async def upsert_embeddings(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Upsert embeddings into ChromaDB collection (v2 API)."""
        collection_id = await self.ensure_collection()
        v2_base = f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{v2_base}/collections/{collection_id}/upsert",
                json={
                    "ids": ids,
                    "embeddings": embeddings,
                    "documents": documents,
                    "metadatas": metadatas,
                },
            )
            resp.raise_for_status()

    async def query_similar(
        self,
        query_embedding: list[float],
        n_results: int = 20,
        where: Optional[dict] = None,
        where_document: Optional[dict] = None,
    ) -> dict:
        """Query ChromaDB for similar items (v2 API).

        Returns: {"ids": [[...]], "distances": [[...]], "metadatas": [[...]], "documents": [[...]]}
        """
        collection_id = await self.ensure_collection()
        v2_base = f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database"
        body = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            body["where"] = where
        if where_document:
            body["where_document"] = where_document

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{v2_base}/collections/{collection_id}/query",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_collection_count(self) -> int:
        """Get number of items in the collection (v2 API)."""
        collection_id = await self.ensure_collection()
        v2_base = f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{v2_base}/collections/{collection_id}/count"
            )
            resp.raise_for_status()
            return resp.json()

    # ── Full pipeline: DB → embed → ChromaDB ─────────────────────

    async def embed_library(
        self,
        db: AsyncSession,
        media_type: str = "movie",
        batch_size: int = 20,
        progress_callback=None,
    ) -> dict:
        """Embed all cached TMDB items that don't have embeddings yet.

        Reads from tmdb_cache, generates embeddings, stores in ChromaDB,
        updates embedding_id back in tmdb_cache.

        Args:
            db: Database session
            media_type: "movie" or "show"
            batch_size: Items per embedding batch (Ollama call)
            progress_callback: async fn(current, total, title)

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
            # Check if any items exist at all
            all_result = await db.execute(
                select(TmdbCache).where(TmdbCache.media_type == media_type)
            )
            all_count = len(list(all_result.scalars().all()))
            return {"embedded": 0, "skipped": all_count, "failed": 0, "total": all_count}

        embedded = 0
        failed = 0
        sync = TmdbSyncService.__new__(TmdbSyncService)  # Just need build_embedding_text

        # Process in batches
        for batch_start in range(0, total, batch_size):
            batch = items[batch_start:batch_start + batch_size]

            # Build texts
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

            # Generate embeddings
            try:
                embeddings = await self.generate_embeddings_batch(texts)
            except Exception as e:
                logger.error(f"Embedding batch failed: {e}")
                failed += len(valid_items)
                continue

            if len(embeddings) != len(valid_items):
                logger.error(f"Embedding count mismatch: {len(embeddings)} vs {len(valid_items)}")
                failed += len(valid_items)
                continue

            # Prepare ChromaDB upsert
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

            # Upsert to ChromaDB
            try:
                await self.upsert_embeddings(ids, embeddings, texts, metadatas)

                # Update embedding_id in DB
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

    async def embed_text_query(self, text: str) -> list[float]:
        """Embed a user query (for Mood Match, search, etc.)."""
        return await self.generate_embedding(f"search_query: {text}")

    async def test_connection(self) -> dict:
        """Test both Ollama and ChromaDB connections."""
        results = {"ollama": False, "chromadb": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                results["ollama"] = resp.status_code == 200
        except Exception:
            pass

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.chromadb_url}/api/v1/heartbeat")
                results["chromadb"] = resp.status_code == 200
        except Exception:
            pass

        return results
