"""Embedding pipeline service.

Generates vector embeddings from TMDB metadata text using Ollama,
stores them in ChromaDB for semantic similarity search.
"""

import httpx
import logging
from typing import Optional



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
                resp = await client.get(f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
                results["chromadb"] = resp.status_code == 200
        except Exception:
            pass

        return results
