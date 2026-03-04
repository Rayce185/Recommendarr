"""Settings store — SQLite-backed with ChromaDB sync.

Replaces the JSON file store. Provides the same interface so callers
don't need to change.
"""

import json
import logging
from typing import Any, Optional
from pathlib import Path
from sqlalchemy import select

from app.database import get_db, DATA_DIR
from app.models.tables import AppSetting

logger = logging.getLogger(__name__)

EDITABLE_FIELDS = {
    "plex_url", "plex_token", "plex_machine_id",
    "tautulli_url", "tautulli_api_key",
    "tmdb_api_key",
    "radarr_url", "radarr_api_key",
    "sonarr_url", "sonarr_api_key",
    "sonarr_anime_url", "sonarr_anime_api_key",
    "seerr_url", "seerr_api_key",
    "llm_base_url", "chromadb_url", "embedding_model",
    "jwt_expiry_hours", "debug", "log_level",
    "recommendarr_port",
}

# Backward compat: if DB isn't ready yet (config import-time), fall back to JSON
SETTINGS_JSON = DATA_DIR / "settings.json"


class SettingsStore:
    """Key/value settings store backed by SQLite."""

    def get(self, key: str, default=None) -> Any:
        """Get a setting by key."""
        try:
            with get_db() as db:
                row = db.execute(
                    select(AppSetting).where(AppSetting.key == key)
                ).scalar_one_or_none()
                if row:
                    return json.loads(row.value)
        except Exception:
            # DB not ready — fall back to JSON
            return self._json_get(key, default)
        return default

    def set(self, key: str, value: Any):
        """Set a setting. Creates or updates."""
        try:
            with get_db() as db:
                row = db.execute(
                    select(AppSetting).where(AppSetting.key == key)
                ).scalar_one_or_none()
                if row:
                    row.value = json.dumps(value)
                else:
                    db.add(AppSetting(key=key, value=json.dumps(value)))
                db.commit()

            # Fire ChromaDB sync (non-blocking)
            from app.services.chroma_sync import get_chroma_sync, fire_and_forget
            sync = get_chroma_sync()
            if sync:
                fire_and_forget(sync.sync_setting(key, value))
        except Exception as e:
            logger.error(f"Settings store set failed: {e}")
            # Fall back to JSON
            self._json_set(key, value)

    def get_all(self) -> dict:
        """Get all settings as a dict."""
        try:
            with get_db() as db:
                rows = db.execute(select(AppSetting)).scalars().all()
                return {r.key: json.loads(r.value) for r in rows}
        except Exception:
            return self._json_get_all()

    def get_all_overrides(self) -> dict:
        """Get all settings as overrides dict (for config.py import-time use)."""
        return self.get_all()

    def delete(self, key: str):
        """Delete a setting."""
        try:
            with get_db() as db:
                row = db.execute(
                    select(AppSetting).where(AppSetting.key == key)
                ).scalar_one_or_none()
                if row:
                    db.delete(row)
                    db.commit()
        except Exception as e:
            logger.error(f"Settings store delete failed: {e}")

    def remove(self, key: str):
        """Alias for delete (backward compat)."""
        self.delete(key)

    def update(self, data: dict):
        """Set multiple keys at once."""
        for key, value in data.items():
            self.set(key, value)

    # ── JSON fallback (used before DB is initialized) ──

    def _json_get(self, key: str, default=None) -> Any:
        if SETTINGS_JSON.exists():
            data = json.loads(SETTINGS_JSON.read_text())
            return data.get(key, default)
        return default

    def _json_set(self, key: str, value: Any):
        data = {}
        if SETTINGS_JSON.exists():
            data = json.loads(SETTINGS_JSON.read_text())
        data[key] = value
        SETTINGS_JSON.write_text(json.dumps(data, indent=2))

    def _json_get_all(self) -> dict:
        if SETTINGS_JSON.exists():
            return json.loads(SETTINGS_JSON.read_text())
        return {}


# Module-level singleton
_store: Optional[SettingsStore] = None


def get_settings_store() -> SettingsStore:
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store
