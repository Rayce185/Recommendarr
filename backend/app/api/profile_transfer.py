"""Profile Export/Import — data portability for user profiles.

GET  /users/{username}/profile/export  — Download feedback + overrides as JSON
POST /users/{username}/profile/import  — Upload JSON to merge or replace profile data
"""

import logging
import time
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.feedback import get_feedback_store, FeedbackEntry
from app.services.profile_overrides import get_override_store, ProfileOverrides
from app.services.cache import get_cache

logger = logging.getLogger(__name__)
router = APIRouter()

EXPORT_VERSION = 1


class ImportRequest(BaseModel):
    data: dict
    mode: str = "merge"  # "merge" or "replace"


@router.get("/users/{username}/profile/export")
async def export_profile(
    username: str,
    user: TokenPayload = Depends(get_current_user),
):
    """Export user profile as downloadable JSON."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot export another user's profile")

    feedback_store = get_feedback_store()
    override_store = get_override_store()

    feedback = feedback_store.get_all(username)
    overrides = override_store.get(username)

    export_data = {
        "export_version": EXPORT_VERSION,
        "app": "recommendarr",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "username": username,
        "feedback": [e.to_dict() for e in feedback],
        "profile_overrides": overrides.to_dict(),
        "stats": {
            "feedback_count": len(feedback),
            "thumbs_up": sum(1 for e in feedback if e.action == "up"),
            "thumbs_down": sum(1 for e in feedback if e.action == "down"),
            "dismissed": sum(1 for e in feedback if e.action == "dismiss"),
            "genre_boosts": len(overrides.genre_boosts),
            "genre_blocks": len(overrides.genre_blocks),
        },
    }

    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="recommendarr-profile-{username}.json"',
        },
    )


@router.post("/users/{username}/profile/import")
async def import_profile(
    username: str,
    body: ImportRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Import profile data from exported JSON. Mode: 'merge' (add new) or 'replace' (overwrite)."""
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot import to another user's profile")

    data = body.data
    mode = body.mode

    if data.get("app") != "recommendarr":
        raise HTTPException(400, "Invalid export file — not a Recommendarr profile")

    if data.get("export_version", 0) > EXPORT_VERSION:
        raise HTTPException(400, f"Export version {data['export_version']} is newer than supported ({EXPORT_VERSION})")

    feedback_store = get_feedback_store()
    override_store = get_override_store()
    imported = {"feedback": 0, "overrides_updated": False}

    # ── Import feedback ──────────────────────────────────────
    raw_feedback = data.get("feedback", [])
    if raw_feedback:
        if mode == "replace":
            # Clear existing and replace
            feedback_store._feedback[username] = []

        existing_ids = {e.tmdb_id for e in feedback_store.get_all(username)}
        for entry_dict in raw_feedback:
            try:
                entry = FeedbackEntry.from_dict(entry_dict)
                if mode == "replace" or entry.tmdb_id not in existing_ids:
                    feedback_store.add(username, entry)
                    imported["feedback"] += 1
            except Exception as e:
                logger.warning("Skipped invalid feedback entry: %s", e)

    # ── Import profile overrides ─────────────────────────────
    raw_overrides = data.get("profile_overrides")
    if raw_overrides:
        if mode == "replace":
            overrides = ProfileOverrides.from_dict(raw_overrides)
        else:
            # Merge: combine boosts, union blocks/keywords
            existing = override_store.get(username)
            merged_boosts = {**existing.genre_boosts}
            for genre, boost in raw_overrides.get("genre_boosts", {}).items():
                if genre not in merged_boosts:
                    merged_boosts[genre] = boost

            merged_blocks = list(set(existing.genre_blocks + raw_overrides.get("genre_blocks", [])))
            merged_kw_boosts = list(set(existing.keyword_boosts + raw_overrides.get("keyword_boosts", [])))
            merged_kw_blocks = list(set(existing.keyword_blocks + raw_overrides.get("keyword_blocks", [])))

            overrides = ProfileOverrides(
                genre_boosts=merged_boosts,
                genre_blocks=merged_blocks,
                keyword_boosts=merged_kw_boosts,
                keyword_blocks=merged_kw_blocks,
                domains=raw_overrides.get("domains", existing.domains),
            )

        override_store.set(username, overrides)
        imported["overrides_updated"] = True

    # Invalidate caches
    get_cache().invalidate_user(username)

    return {
        "status": "ok",
        "mode": mode,
        "imported_feedback": imported["feedback"],
        "overrides_updated": imported["overrides_updated"],
    }
