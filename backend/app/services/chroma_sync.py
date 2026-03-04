"""ChromaDB sync layer — vectorizes DB writes for RAG pipeline.

When configured, every meaningful write to SQLite gets:
1. Serialized to a natural-language text chunk
2. Embedded via configured model (e.g. nomic-embed-text @ Ollama)
3. Upserted to ChromaDB collection

This is OPTIONAL — runs only when chromadb_url is configured.
Fire-and-forget: sync errors never block the main request path.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Singleton
_sync: Optional["ChromaSync"] = None


class ChromaSync:
    """Async ChromaDB sync client."""

    def __init__(self, chromadb_url: str, embed_url: str, embed_model: str,
                 collection: str = "recommendarr"):
        self.chromadb_url = chromadb_url.rstrip("/")
        self.embed_url = embed_url.rstrip("/")
        self.embed_model = embed_model
        self.collection_name = collection
        self._collection_id: Optional[str] = None
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        logger.info(f"ChromaDB sync initialized: {self.chromadb_url} collection={collection}")

    _BASE = "api/v2/tenants/default_tenant/databases/default_database"

    async def _ensure_collection(self):
        """Create collection if it doesn't exist, cache the ID."""
        if self._collection_id:
            return
        try:
            # List existing collections, find ours
            resp = await self._client.get(
                f"{self.chromadb_url}/{self._BASE}/collections"
            )
            if resp.status_code == 200:
                for col in resp.json():
                    if col.get("name") == self.collection_name:
                        self._collection_id = col["id"]
                        logger.info(f"ChromaDB collection '{self.collection_name}' found (id={self._collection_id[:12]}...)")
                        return

            # Create new
            resp = await self._client.post(
                f"{self.chromadb_url}/{self._BASE}/collections",
                json={"name": self.collection_name}
            )
            resp.raise_for_status()
            self._collection_id = resp.json().get("id")
            logger.info(f"ChromaDB collection '{self.collection_name}' created (id={self._collection_id[:12]}...)")
        except Exception as e:
            logger.warning(f"ChromaDB collection setup failed: {e}")

    async def _embed(self, text: str) -> Optional[list[float]]:
        """Get embedding vector from Ollama-compatible endpoint."""
        try:
            resp = await self._client.post(
                f"{self.embed_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text}
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
        except Exception as e:
            logger.debug(f"Embedding failed: {e}")
            return None

    async def sync_record(self, table: str, record_id: str, text: str,
                          metadata: Optional[dict] = None):
        """Embed and upsert a single record to ChromaDB.

        Args:
            table: Source table name (e.g. "feedback", "request_log")
            record_id: Unique ID within table (e.g. "42")
            text: Natural language representation for embedding
            metadata: Structured metadata for filtering
        """
        try:
            await self._ensure_collection()
            if not self._collection_id:
                return

            embedding = await self._embed(text)
            if not embedding:
                return

            doc_id = f"{table}:{record_id}"
            meta = {
                "table": table,
                "record_id": str(record_id),
                "synced_at": datetime.utcnow().isoformat(),
                **(metadata or {}),
            }
            # Filter out None values (ChromaDB rejects them)
            meta = {k: v for k, v in meta.items() if v is not None}

            await self._client.post(
                f"{self.chromadb_url}/{self._BASE}/collections/{self._collection_id}/upsert",
                json={
                    "ids": [doc_id],
                    "embeddings": [embedding],
                    "documents": [text],
                    "metadatas": [meta],
                }
            )
            logger.debug(f"ChromaDB sync: {doc_id}")
        except Exception as e:
            logger.debug(f"ChromaDB sync failed for {table}:{record_id}: {e}")

    async def sync_feedback(self, username: str, tmdb_id: int, media_type: str,
                            title: str, action: str):
        """Sync a feedback event (thumbs up/down/dismiss)."""
        text = f"User '{username}' gave {action} feedback on {media_type} '{title}' (TMDB {tmdb_id})"
        await self.sync_record("feedback", f"{username}:{tmdb_id}", text, {
            "username": username, "tmdb_id": tmdb_id, "media_type": media_type,
            "title": title, "action": action, "type": "feedback",
        })

    async def sync_request(self, username: str, tmdb_id: int, media_type: str,
                           title: str, instance: str, root_folder: str, status: str):
        """Sync a library add request."""
        text = (f"User '{username}' requested {media_type} '{title}' (TMDB {tmdb_id}). "
                f"Routed to {instance}:{root_folder}. Status: {status}")
        await self.sync_record("request_log", f"{username}:{tmdb_id}", text, {
            "username": username, "tmdb_id": tmdb_id, "media_type": media_type,
            "title": title, "instance": instance, "status": status, "type": "request",
        })

    async def sync_preference(self, username: str, key: str, value):
        """Sync a user preference change."""
        text = f"User '{username}' set preference '{key}' to '{value}'"
        await self.sync_record("user_preferences", f"{username}:{key}", text, {
            "username": username, "pref_key": key, "type": "preference",
        })

    async def sync_taste_profile(self, username: str, profile_summary: str):
        """Sync a taste profile update."""
        text = f"Taste profile for '{username}': {profile_summary}"
        await self.sync_record("taste_profile", username, text, {
            "username": username, "type": "taste_profile",
        })

    async def sync_setting(self, key: str, value):
        """Sync an app setting change."""
        # Don't sync sensitive keys
        sensitive = {"plex_token", "radarr_api_key", "sonarr_api_key",
                     "sonarr_anime_api_key", "seerr_api_key", "tmdb_api_key",
                     "jwt_secret", "llm_api_key"}
        if key in sensitive:
            return
        text = f"App setting '{key}' set to '{value}'"
        await self.sync_record("app_settings", key, text, {
            "setting_key": key, "type": "setting",
        })

    async def close(self):
        await self._client.aclose()


def get_chroma_sync() -> Optional[ChromaSync]:
    """Get the singleton ChromaSync instance, or None if not configured."""
    return _sync


def init_chroma_sync(chromadb_url: str, embed_url: str, embed_model: str,
                     collection: str = "recommendarr"):
    """Initialize ChromaDB sync (called from app startup if configured)."""
    global _sync
    if chromadb_url and embed_url and embed_model:
        _sync = ChromaSync(chromadb_url, embed_url, embed_model, collection)
        return _sync
    return None


def fire_and_forget(coro):
    """Schedule a coroutine without waiting for it. Errors logged, never raised."""
    try:
        loop = asyncio.get_event_loop()
        task = loop.create_task(coro)
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
    except RuntimeError:
        pass  # No event loop — skip sync
