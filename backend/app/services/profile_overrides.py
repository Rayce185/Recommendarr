"""User profile overrides — manual taste adjustments on top of computed profile.

Stores genre boosts/blocks, keyword preferences, and domain toggles.
In-memory storage for now; persist to file for durability later.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

OVERRIDES_FILE = "/app/data/profile_overrides.json"


@dataclass
class ProfileOverrides:
    """User's manual taste adjustments."""
    genre_boosts: dict[str, float] = field(default_factory=dict)    # genre -> -1.0 to 1.0
    genre_blocks: list[str] = field(default_factory=list)           # genres to never recommend
    keyword_boosts: list[str] = field(default_factory=list)         # keywords to prefer
    keyword_blocks: list[str] = field(default_factory=list)         # keywords to avoid
    domains: dict[str, bool] = field(default_factory=lambda: {"movies": True, "tv": True, "anime": True})
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "genre_boosts": self.genre_boosts,
            "genre_blocks": self.genre_blocks,
            "keyword_boosts": self.keyword_boosts,
            "keyword_blocks": self.keyword_blocks,
            "domains": self.domains,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProfileOverrides":
        return cls(
            genre_boosts=d.get("genre_boosts", {}),
            genre_blocks=d.get("genre_blocks", []),
            keyword_boosts=d.get("keyword_boosts", []),
            keyword_blocks=d.get("keyword_blocks", []),
            domains=d.get("domains", {"movies": True, "tv": True, "anime": True}),
            updated_at=d.get("updated_at", ""),
        )


class ProfileOverrideStore:
    """In-memory store for profile overrides with file persistence."""

    def __init__(self):
        self._overrides: dict[str, ProfileOverrides] = {}
        self._load_from_disk()

    def get(self, username: str) -> ProfileOverrides:
        return self._overrides.get(username, ProfileOverrides())

    def set(self, username: str, overrides: ProfileOverrides):
        import datetime
        overrides.updated_at = datetime.datetime.now().isoformat()
        self._overrides[username] = overrides
        self._save_to_disk()
        logger.info(f"Profile overrides saved for {username}: {len(overrides.genre_boosts)} genre boosts, {len(overrides.genre_blocks)} blocks")

    def get_updated_at(self, username: str) -> str:
        o = self._overrides.get(username)
        return o.updated_at if o else ""

    def _load_from_disk(self):
        try:
            if os.path.exists(OVERRIDES_FILE):
                with open(OVERRIDES_FILE, "r") as f:
                    data = json.load(f)
                for username, d in data.items():
                    self._overrides[username] = ProfileOverrides.from_dict(d)
                logger.info(f"Loaded profile overrides for {len(self._overrides)} users from disk")
        except Exception as e:
            logger.warning(f"Failed to load profile overrides: {e}")

    def _save_to_disk(self):
        try:
            os.makedirs(os.path.dirname(OVERRIDES_FILE), exist_ok=True)
            with open(OVERRIDES_FILE, "w") as f:
                json.dump({u: o.to_dict() for u, o in self._overrides.items()}, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save profile overrides: {e}")


# Singleton
_store: Optional[ProfileOverrideStore] = None

def get_override_store() -> ProfileOverrideStore:
    global _store
    if _store is None:
        _store = ProfileOverrideStore()
    return _store
