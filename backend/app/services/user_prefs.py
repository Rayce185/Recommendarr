"""User preferences — SQLite-backed with hierarchical resolution.

Resolution order: user-specific > global > hardcoded defaults.
ChromaDB sync fires on every preference change.
"""

import json
import logging
from typing import Any, Optional
from sqlalchemy import select, and_

from app.database import get_db
from app.models.tables import UserPreference

logger = logging.getLogger(__name__)

DEFAULTS = {
    "default_mode": "grab",
    "default_limit": 20,
    "genre_filter": None,
    "media_type_filter": None,
    "default_device_id": None,
    "ui_theme": "dark",
    "show_explanations": True,
    "show_trailers": True,
    "language": "en",
}


class UserPrefsService:
    """Hierarchical preferences: user → global → defaults."""

    def get(self, username: str, key: str, default=None) -> Any:
        """Get a preference with hierarchical fallback."""
        try:
            with get_db() as db:
                # User-specific first
                row = db.execute(
                    select(UserPreference).where(
                        and_(UserPreference.username == username, UserPreference.key == key)
                    )
                ).scalar_one_or_none()
                if row:
                    return json.loads(row.value)

                # Global fallback
                row = db.execute(
                    select(UserPreference).where(
                        and_(UserPreference.username == "_global", UserPreference.key == key)
                    )
                ).scalar_one_or_none()
                if row:
                    return json.loads(row.value)
        except Exception as e:
            logger.debug(f"UserPrefs get failed: {e}")

        # Hardcoded defaults
        return DEFAULTS.get(key, default)

    def get_all(self, username: str) -> dict:
        """Get all preferences for a user (merged with globals and defaults)."""
        result = dict(DEFAULTS)
        try:
            with get_db() as db:
                # Layer global
                globals_ = db.execute(
                    select(UserPreference).where(UserPreference.username == "_global")
                ).scalars().all()
                for row in globals_:
                    result[row.key] = json.loads(row.value)

                # Layer user-specific (overrides globals)
                if username != "_global":
                    user_rows = db.execute(
                        select(UserPreference).where(UserPreference.username == username)
                    ).scalars().all()
                    for row in user_rows:
                        result[row.key] = json.loads(row.value)
        except Exception as e:
            logger.debug(f"UserPrefs get_all failed: {e}")
        return result

    def set(self, username: str, key: str, value: Any):
        """Set a preference for a user (or _global)."""
        try:
            with get_db() as db:
                row = db.execute(
                    select(UserPreference).where(
                        and_(UserPreference.username == username, UserPreference.key == key)
                    )
                ).scalar_one_or_none()
                if row:
                    row.value = json.dumps(value)
                else:
                    db.add(UserPreference(username=username, key=key, value=json.dumps(value)))
                db.commit()

            # ChromaDB sync
            from app.services.chroma_sync import get_chroma_sync, fire_and_forget
            sync = get_chroma_sync()
            if sync:
                fire_and_forget(sync.sync_preference(username, key, value))
        except Exception as e:
            logger.error(f"UserPrefs set failed: {e}")

    def set_many(self, username: str, prefs: dict):
        """Set multiple preferences at once."""
        try:
            with get_db() as db:
                for key, value in prefs.items():
                    row = db.execute(
                        select(UserPreference).where(
                            and_(UserPreference.username == username, UserPreference.key == key)
                        )
                    ).scalar_one_or_none()
                    if row:
                        row.value = json.dumps(value)
                    else:
                        db.add(UserPreference(username=username, key=key, value=json.dumps(value)))
                db.commit()
        except Exception as e:
            logger.error(f"UserPrefs set_many failed: {e}")

    def get_user_overrides(self, username: str) -> dict:
        """Get only user-specific overrides (not globals or defaults)."""
        result = {}
        try:
            with get_db() as db:
                rows = db.execute(
                    select(UserPreference).where(UserPreference.username == username)
                ).scalars().all()
                for row in rows:
                    result[row.key] = json.loads(row.value)
        except Exception as e:
            logger.debug(f"UserPrefs get_user_overrides failed: {e}")
        return result

    def set_user(self, username: str, updates: dict) -> dict:
        """Set multiple user preferences. Returns saved keys."""
        self.set_many(username, updates)
        return updates

    def get_flat(self, username: str) -> dict:
        """Get all preferences as flat values (no source metadata)."""
        return self.get_all(username)

    def get_global_defaults(self) -> dict:
        """Get global defaults with source annotations."""
        result = {}
        for key, default in DEFAULTS.items():
            result[key] = {"value": default, "source": "default"}
        try:
            with get_db() as db:
                rows = db.execute(
                    select(UserPreference).where(UserPreference.username == "_global")
                ).scalars().all()
                for row in rows:
                    result[row.key] = {"value": json.loads(row.value), "source": "global"}
        except Exception:
            pass
        return result

    def get_global(self) -> dict:
        """Get global settings with source annotation (for admin UI)."""
        return self.get_global_defaults()

    def set_global(self, updates: dict) -> dict:
        """Set global default preferences."""
        self.set_many("_global", updates)
        return updates

    def delete(self, username: str, key: str):
        """Delete a specific preference."""
        try:
            with get_db() as db:
                row = db.execute(
                    select(UserPreference).where(
                        and_(UserPreference.username == username, UserPreference.key == key)
                    )
                ).scalar_one_or_none()
                if row:
                    db.delete(row)
                    db.commit()
        except Exception as e:
            logger.error(f"UserPrefs delete failed: {e}")


# Singleton
_prefs: Optional[UserPrefsService] = None


def get_user_prefs() -> UserPrefsService:
    global _prefs
    if _prefs is None:
        _prefs = UserPrefsService()
    return _prefs
