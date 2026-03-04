"""Per-user preferences with global defaults cascade.

Resolution order (highest wins):
1. User-specific value in /app/data/user_prefs/{username}.json
2. Global defaults in /app/data/user_prefs/_global.json
3. Code defaults (PREF_DEFAULTS below)

Admin can set global defaults that apply to all users who haven't
overridden that specific setting. Per-user changes only affect that user.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

PREFS_DIR = Path("/app/data/user_prefs")
GLOBAL_FILE = PREFS_DIR / "_global.json"

# Code-level defaults for all preference keys
PREF_DEFAULTS = {
    # Watchlist
    "watchlist_sort": "addedAt:desc",         # addedAt:desc|asc, titleSort:asc|desc, year:desc|asc, rating:desc|asc
    "watchlist_filter": "all",                # all | movie | tv

    # Playback
    "default_device_id": "",                  # Plex clientIdentifier for "Watch Now"
    "default_device_name": "",                # Display name (cached for UI)

    # AI
    "ai_temperature": 0.7,
    "ai_explanations_enabled": True,
    "ai_mood_enabled": True,

    # Display
    "hide_watched": False,
    "cards_per_row": 0,                       # 0 = auto
    "language": "en",                         # en | de
}

# Keys that are valid for global defaults (admin-controlled)
GLOBAL_KEYS = {
    "ai_temperature", "ai_explanations_enabled", "ai_mood_enabled",
    "hide_watched", "cards_per_row", "language",
    "watchlist_sort", "watchlist_filter",
}


class UserPrefsStore:
    """Manages per-user preferences with global defaults."""

    def __init__(self):
        PREFS_DIR.mkdir(parents=True, exist_ok=True)
        import os
        os.chmod(str(PREFS_DIR), 0o777)
        self._cache: dict[str, dict] = {}

    def _user_file(self, username: str) -> Path:
        # Sanitize username for filesystem
        safe = "".join(c for c in username if c.isalnum() or c in "-_.")
        return PREFS_DIR / f"{safe}.json"

    def _load_file(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load {path}: {e}")
        return {}

    def _save_file(self, path: Path, data: dict):
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_global(self) -> dict:
        return self._load_file(GLOBAL_FILE)

    def _load_user(self, username: str) -> dict:
        return self._load_file(self._user_file(username))

    # ── Public API ─────────────────────────────────────────────────

    def get(self, username: str, key: str) -> Any:
        """Get a single preference value (user → global → default)."""
        user_data = self._load_user(username)
        if key in user_data:
            return user_data[key]
        global_data = self._load_global()
        if key in global_data:
            return global_data[key]
        return PREF_DEFAULTS.get(key)

    def get_all(self, username: str) -> dict:
        """Get all resolved preferences for a user.

        Returns dict with resolved values + metadata about source.
        """
        global_data = self._load_global()
        user_data = self._load_user(username)

        result = {}
        for key, default in PREF_DEFAULTS.items():
            if key in user_data:
                result[key] = {"value": user_data[key], "source": "user"}
            elif key in global_data:
                result[key] = {"value": global_data[key], "source": "global"}
            else:
                result[key] = {"value": default, "source": "default"}
        return result

    def get_flat(self, username: str) -> dict:
        """Get all resolved preference values (flat dict, no source info)."""
        return {k: v["value"] for k, v in self.get_all(username).items()}

    def set_user(self, username: str, updates: dict) -> dict:
        """Set per-user preferences. Returns updated user prefs."""
        user_data = self._load_user(username)
        for k, v in updates.items():
            if k in PREF_DEFAULTS:
                user_data[k] = v
        self._save_file(self._user_file(username), user_data)
        return user_data

    def reset_user_key(self, username: str, key: str) -> bool:
        """Reset a single user pref to inherit from global/default."""
        user_data = self._load_user(username)
        if key in user_data:
            del user_data[key]
            self._save_file(self._user_file(username), user_data)
            return True
        return False

    def set_global(self, updates: dict) -> dict:
        """Set global default preferences (admin only). Returns updated globals."""
        global_data = self._load_global()
        for k, v in updates.items():
            if k in GLOBAL_KEYS:
                global_data[k] = v
        self._save_file(GLOBAL_FILE, global_data)
        return global_data

    def get_global(self) -> dict:
        """Get global defaults with metadata."""
        global_data = self._load_global()
        result = {}
        for key in GLOBAL_KEYS:
            default = PREF_DEFAULTS.get(key)
            if key in global_data:
                result[key] = {"value": global_data[key], "source": "global"}
            else:
                result[key] = {"value": default, "source": "default"}
        return result

    def get_user_overrides(self, username: str) -> dict:
        """Get only the keys the user has explicitly overridden."""
        return self._load_user(username)


# Singleton
_store: Optional[UserPrefsStore] = None


def get_user_prefs() -> UserPrefsStore:
    global _store
    if _store is None:
        _store = UserPrefsStore()
    return _store
