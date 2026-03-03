"""Persistent settings store — JSON file overlay on top of env vars.

Settings hierarchy (highest wins):
1. Runtime overrides from /app/data/settings.json
2. Environment variables / .env file
3. Pydantic defaults in config.py

The store only persists fields that were explicitly saved by the admin.
Unsaved fields continue to read from env vars as before.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

SETTINGS_FILE = Path("/app/data/settings.json")

# Fields that can be edited via the UI
EDITABLE_FIELDS = {
    # Service URLs
    "plex_url", "tautulli_url", "radarr_url", "sonarr_url",
    "sonarr_anime_url", "seerr_url",
    # Service API keys
    "plex_token", "tautulli_api_key", "radarr_api_key", "sonarr_api_key",
    "sonarr_anime_api_key", "seerr_api_key", "tmdb_api_key",
    # Plex
    "plex_machine_id",
    # LLM
    "llm_base_url", "chromadb_url", "embedding_model",
    # Auth
    "jwt_expiry_hours",
    # App
    "debug", "log_level",
}

# Fields that must NEVER be exposed or editable via API
PROTECTED_FIELDS = {"jwt_secret", "database_url"}


class SettingsStore:
    """Read/write persistent settings overlay."""

    def __init__(self):
        self._overrides: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load overrides from JSON file."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                # Only load known editable fields
                self._overrides = {
                    k: v for k, v in data.items()
                    if k in EDITABLE_FIELDS
                }
            except (json.JSONDecodeError, OSError) as e:
                print(f"[settings_store] Failed to load {SETTINGS_FILE}: {e}")
                self._overrides = {}

    def _save(self):
        """Persist current overrides to JSON."""
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self._overrides, f, indent=2)

    def get(self, field: str) -> Optional[Any]:
        """Get override value for a field, or None if not overridden."""
        return self._overrides.get(field)

    def has_override(self, field: str) -> bool:
        """Check if a field has a persistent override."""
        return field in self._overrides

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Update multiple fields. Returns the saved values.

        Only accepts EDITABLE_FIELDS. Silently ignores protected/unknown fields.
        """
        changed = {}
        for k, v in updates.items():
            if k in EDITABLE_FIELDS:
                self._overrides[k] = v
                changed[k] = v
        if changed:
            self._save()
        return changed

    def remove(self, field: str) -> bool:
        """Remove an override, reverting to env var value."""
        if field in self._overrides:
            del self._overrides[field]
            self._save()
            return True
        return False

    def get_all_overrides(self) -> dict[str, Any]:
        """Get all current overrides."""
        return dict(self._overrides)


# Singleton
_store: Optional[SettingsStore] = None


def get_settings_store() -> SettingsStore:
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store
