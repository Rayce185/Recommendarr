"""Kick executor — handles Radarr/Sonarr deletion + metadata snapshot.

Responsible for:
1. Snapshotting item metadata before deletion
2. Exporting JSON backup to disk
3. Deleting from Radarr/Sonarr via API
4. Recording in kicked_items table
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.library_health import KickedItem, SunsetItem, VitalityScore
from app.services.vitality_scoring import estimate_redownload_tier

logger = logging.getLogger(__name__)

# JSON backup directory
KICKED_BACKUP_DIR = Path(os.getenv("DATA_DIR", "/app/data")) / "kicked"


async def execute_kick(tmdb_id: int, media_type: str) -> dict:
    """Execute a confirmed kick: snapshot → backup → delete → record.

    Only operates on items with status='approved' in sunset_items.
    Returns summary of the operation.
    """
    from app.services.factory import get_stack

    db = get_db()
    try:
        # 1. Verify the item is approved for kicking
        sunset = db.execute(
            select(SunsetItem).where(
                SunsetItem.tmdb_id == tmdb_id,
                SunsetItem.media_type == media_type,
                SunsetItem.status == "approved",
            )
        ).scalar_one_or_none()

        if not sunset:
            raise ValueError(f"No approved kick for tmdb={tmdb_id} type={media_type}")

        stack = get_stack()

        # 2. Snapshot metadata from Radarr/Sonarr before deletion
        snapshot = await _snapshot_servarr_item(
            stack, tmdb_id, media_type, sunset.servarr_id,
        )

        # 3. Get vitality score for context
        vitality = db.execute(
            select(VitalityScore).where(
                VitalityScore.tmdb_id == tmdb_id,
                VitalityScore.media_type == media_type,
            )
        ).scalar_one_or_none()
        vitality_score = vitality.composite_score if vitality else 0.0

        # 4. Estimate re-download tier
        eta_tier = estimate_redownload_tier(
            snapshot.get("popularity"),
            snapshot.get("year"),
            snapshot.get("original_language"),
        )

        # 5. Record in kicked_items (SQLite primary)
        kicked = KickedItem(
            tmdb_id=tmdb_id, media_type=media_type,
            title=snapshot.get("title", "Unknown"),
            servarr_id=sunset.servarr_id or 0,
            servarr_type="radarr" if media_type == "movie" else "sonarr",
            quality_profile_id=snapshot.get("quality_profile_id"),
            quality_profile_name=snapshot.get("quality_profile_name"),
            root_folder=snapshot.get("root_folder"),
            tags=snapshot.get("tags"),
            poster_path=snapshot.get("poster_path"),
            year=snapshot.get("year"),
            genres=snapshot.get("genres"),
            overview=snapshot.get("overview"),
            vitality_at_kick=vitality_score,
            kicked_by=sunset.kick_method or "vote",
            redownload_eta_tier=eta_tier,
        )
        db.add(kicked)

        # 6. Export JSON backup
        _export_json_backup(kicked, snapshot)

        # 7. Delete from Radarr/Sonarr
        deleted = await _delete_from_servarr(
            stack, tmdb_id, media_type, sunset.servarr_id,
        )

        # 8. Update sunset item status
        sunset.status = "kicked"
        sunset.resolved_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Kicked: %s [tmdb=%d] method=%s vitality=%.1f eta=%s deleted=%s",
            snapshot.get("title"), tmdb_id, sunset.kick_method,
            vitality_score, eta_tier, deleted,
        )

        return {
            "tmdb_id": tmdb_id,
            "title": snapshot.get("title"),
            "kicked_by": sunset.kick_method,
            "vitality_at_kick": vitality_score,
            "eta_tier": eta_tier,
            "deleted_from_servarr": deleted,
        }

    except Exception as e:
        db.rollback()
        logger.error("Kick execution failed for tmdb=%d: %s", tmdb_id, e, exc_info=True)
        raise
    finally:
        db.close()


async def _snapshot_servarr_item(
    stack, tmdb_id: int, media_type: str, servarr_id: Optional[int],
) -> dict:
    """Capture full metadata from Radarr/Sonarr before deletion."""
    snapshot = {"tmdb_id": tmdb_id, "media_type": media_type}

    try:
        if media_type == "movie":
            movies = await stack.registry.get_all_movies()
            for m in movies:
                if m.tmdb_id == tmdb_id or m.radarr_id == servarr_id:
                    snapshot.update({
                        "title": m.title, "year": m.year,
                        "genres": m.genres, "overview": m.overview,
                        "poster_path": m.poster_path,
                        "original_language": m.original_language,
                        "popularity": m.popularity,
                        "quality": m.quality,
                        "tags": m.tags,
                        "radarr_id": m.radarr_id,
                    })
                    # Get quality profile + root folder from Radarr API
                    client = stack.registry.get_default_for("movie")
                    if client:
                        profiles = await client.get_quality_profiles()
                        folders = await client.get_root_folders()
                        snapshot["quality_profile_id"] = None
                        snapshot["quality_profile_name"] = None
                        snapshot["root_folder"] = folders[0]["path"] if folders else None
                        for p in profiles:
                            snapshot["quality_profile_id"] = p["id"]
                            snapshot["quality_profile_name"] = p["name"]
                            break  # first profile as default
                    break
        else:
            # Series from Sonarr
            for inst_name, client in stack.registry.get_by_type("sonarr"):
                if client:
                    series_list = await client.get_all_series()
                    for s in series_list:
                        if s.tmdb_id == tmdb_id or s.sonarr_id == servarr_id:
                            snapshot.update({
                                "title": s.title, "year": s.year,
                                "genres": s.genres, "overview": s.overview,
                                "poster_path": s.poster_path,
                                "original_language": s.original_language,
                                "tags": s.tags,
                                "sonarr_id": s.sonarr_id,
                            })
                            break
    except Exception as e:
        logger.warning("Snapshot incomplete for tmdb=%d: %s", tmdb_id, e)

    return snapshot


def _export_json_backup(kicked: KickedItem, snapshot: dict):
    """Write JSON backup file for disaster recovery."""
    try:
        KICKED_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{kicked.tmdb_id}_{kicked.media_type}_{kicked.kicked_at.strftime('%Y%m%d')}.json"
        filepath = KICKED_BACKUP_DIR / filename

        backup_data = {
            "tmdb_id": kicked.tmdb_id,
            "media_type": kicked.media_type,
            "title": kicked.title,
            "servarr_id": kicked.servarr_id,
            "servarr_type": kicked.servarr_type,
            "quality_profile_id": kicked.quality_profile_id,
            "quality_profile_name": kicked.quality_profile_name,
            "root_folder": kicked.root_folder,
            "tags": kicked.tags,
            "year": kicked.year,
            "genres": kicked.genres,
            "overview": kicked.overview,
            "vitality_at_kick": kicked.vitality_at_kick,
            "kicked_at": kicked.kicked_at.isoformat(),
            "kicked_by": kicked.kicked_by,
            "eta_tier": kicked.redownload_eta_tier,
            "full_snapshot": snapshot,
        }

        filepath.write_text(json.dumps(backup_data, indent=2, default=str))
        logger.info("JSON backup exported: %s", filepath)
    except Exception as e:
        logger.error("Failed to export JSON backup: %s", e)
        # Non-fatal — SQLite record is the primary


async def _delete_from_servarr(
    stack, tmdb_id: int, media_type: str, servarr_id: Optional[int],
) -> bool:
    """Delete item from Radarr/Sonarr. Returns True if deleted."""
    import httpx

    try:
        if media_type == "movie":
            client = stack.registry.get_default_for("movie")
            if client and servarr_id:
                async with httpx.AsyncClient(timeout=30.0) as http:
                    resp = await http.delete(
                        f"{client.url}/api/v3/movie/{servarr_id}",
                        headers=client.headers,
                        params={"deleteFiles": "true", "addImportExclusion": "false"},
                    )
                    return resp.status_code in (200, 204)
        else:
            for inst_name, client in stack.registry.get_by_type("sonarr"):
                client = stack.registry.get(inst)
                if client and servarr_id:
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        resp = await http.delete(
                            f"{client.url}/api/v3/series/{servarr_id}",
                            headers=client.headers,
                            params={"deleteFiles": "true"},
                        )
                        if resp.status_code in (200, 204):
                            return True
    except Exception as e:
        logger.error("Servarr deletion failed for tmdb=%d: %s", tmdb_id, e)
        return False

    return False
