"""User feedback store — thumbs up/down/dismiss on recommendations.

Persists to JSON file. Feedback feeds back into recommendation scoring:
  - thumbs_up: +0.15 score boost on genre/keyword overlap with liked items
  - thumbs_down: -0.15 penalty on genre/keyword overlap with disliked items
  - dismiss: excluded from future results for that user
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

FEEDBACK_FILE = "/app/data/user_feedback.json"


@dataclass
class FeedbackEntry:
    tmdb_id: int
    media_type: str         # "movie" or "tv"
    action: str             # "up", "down", "dismiss"
    title: str = ""
    genres: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    reason: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tmdb_id": self.tmdb_id,
            "media_type": self.media_type,
            "action": self.action,
            "title": self.title,
            "genres": self.genres,
            "keywords": self.keywords,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeedbackEntry":
        return cls(
            tmdb_id=d["tmdb_id"],
            media_type=d.get("media_type", "movie"),
            action=d["action"],
            title=d.get("title", ""),
            genres=d.get("genres", []),
            keywords=d.get("keywords", []),
            reason=d.get("reason", ""),
            timestamp=d.get("timestamp", 0.0),
        )


class FeedbackStore:
    """In-memory feedback store with file persistence."""

    def __init__(self):
        self._feedback: dict[str, list[FeedbackEntry]] = {}  # username -> entries
        self._load_from_disk()

    def add(self, username: str, entry: FeedbackEntry):
        """Add or update feedback for a specific item."""
        if username not in self._feedback:
            self._feedback[username] = []

        entry.timestamp = time.time()

        # Replace existing feedback for same tmdb_id (user changed their mind)
        self._feedback[username] = [
            e for e in self._feedback[username]
            if e.tmdb_id != entry.tmdb_id
        ]
        self._feedback[username].append(entry)
        self._save_to_disk()
        logger.info(f"Feedback: {username} → {entry.action} on {entry.title or entry.tmdb_id}")

    def remove(self, username: str, tmdb_id: int):
        """Remove feedback for a specific item."""
        if username in self._feedback:
            self._feedback[username] = [
                e for e in self._feedback[username]
                if e.tmdb_id != tmdb_id
            ]
            self._save_to_disk()

    def get_all(self, username: str) -> list[FeedbackEntry]:
        return self._feedback.get(username, [])

    def get_action(self, username: str, tmdb_id: int) -> Optional[str]:
        """Get feedback action for a specific item, or None."""
        for e in self._feedback.get(username, []):
            if e.tmdb_id == tmdb_id:
                return e.action
        return None

    def get_dismissed_ids(self, username: str) -> set[int]:
        """IDs the user dismissed — exclude from results."""
        return {
            e.tmdb_id for e in self._feedback.get(username, [])
            if e.action == "dismiss"
        }

    def get_liked_genres(self, username: str) -> dict[str, int]:
        """Genre frequency from thumbs-up items."""
        counts: dict[str, int] = {}
        for e in self._feedback.get(username, []):
            if e.action == "up":
                for g in e.genres:
                    counts[g] = counts.get(g, 0) + 1
        return counts

    def get_disliked_genres(self, username: str) -> dict[str, int]:
        """Genre frequency from thumbs-down items."""
        counts: dict[str, int] = {}
        for e in self._feedback.get(username, []):
            if e.action == "down":
                for g in e.genres:
                    counts[g] = counts.get(g, 0) + 1
        return counts

    def get_stats(self, username: str) -> dict:
        entries = self._feedback.get(username, [])
        return {
            "total": len(entries),
            "thumbs_up": sum(1 for e in entries if e.action == "up"),
            "thumbs_down": sum(1 for e in entries if e.action == "down"),
            "dismissed": sum(1 for e in entries if e.action == "dismiss"),
        }

    def _load_from_disk(self):
        try:
            if os.path.exists(FEEDBACK_FILE):
                with open(FEEDBACK_FILE, "r") as f:
                    data = json.load(f)
                for username, entries in data.items():
                    self._feedback[username] = [FeedbackEntry.from_dict(e) for e in entries]
                total = sum(len(v) for v in self._feedback.values())
                logger.info(f"Loaded {total} feedback entries for {len(self._feedback)} users")
        except Exception as e:
            logger.warning(f"Failed to load feedback: {e}")

    def _save_to_disk(self):
        try:
            os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
            with open(FEEDBACK_FILE, "w") as f:
                json.dump(
                    {u: [e.to_dict() for e in entries] for u, entries in self._feedback.items()},
                    f, indent=2
                )
        except Exception as e:
            logger.warning(f"Failed to save feedback: {e}")


# Singleton
_store: Optional[FeedbackStore] = None

def get_feedback_store() -> FeedbackStore:
    global _store
    if _store is None:
        _store = FeedbackStore()
    return _store
