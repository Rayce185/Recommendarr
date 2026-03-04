"""JSON → SQLite migration — runs once on first startup with DB."""

import json
import logging
import os
from pathlib import Path
from sqlalchemy import select
from app.database import get_db, DATA_DIR
from app.models.tables import AppSetting, UserPreference, AiSetting

logger = logging.getLogger(__name__)

SETTINGS_JSON = DATA_DIR / "settings.json"
AI_CONFIG_JSON = DATA_DIR / "ai_config.json"
USER_PREFS_DIR = DATA_DIR / "user_prefs"
MIGRATION_MARKER = DATA_DIR / ".migrated_to_sqlite"


def needs_migration() -> bool:
    """Check if JSON files exist and haven't been migrated yet."""
    if MIGRATION_MARKER.exists():
        return False
    return SETTINGS_JSON.exists() or AI_CONFIG_JSON.exists() or USER_PREFS_DIR.exists()


def migrate_json_to_sqlite():
    """One-time migration of JSON config files into SQLite."""
    if not needs_migration():
        return

    logger.info("Migrating JSON config files to SQLite...")
    migrated = 0

    with get_db() as db:
        # 1. settings.json → app_settings
        if SETTINGS_JSON.exists():
            try:
                data = json.loads(SETTINGS_JSON.read_text())
                for key, value in data.items():
                    existing = db.execute(
                        select(AppSetting).where(AppSetting.key == key)
                    ).scalar_one_or_none()
                    if not existing:
                        db.add(AppSetting(key=key, value=json.dumps(value)))
                db.commit()
                migrated += len(data)
                logger.info(f"  Migrated {len(data)} settings from settings.json")
            except Exception as e:
                db.rollback()
                logger.error(f"  Failed to migrate settings.json: {e}")

        # 2. ai_config.json → ai_settings
        if AI_CONFIG_JSON.exists():
            try:
                data = json.loads(AI_CONFIG_JSON.read_text())
                # Flatten nested config: llm.provider → llm_provider, etc.
                flat = {}
                for section, values in data.items():
                    if isinstance(values, dict):
                        for k, v in values.items():
                            flat[f"{section}_{k}"] = v
                    else:
                        flat[section] = values
                for key, value in flat.items():
                    existing = db.execute(
                        select(AiSetting).where(AiSetting.key == key)
                    ).scalar_one_or_none()
                    if not existing:
                        db.add(AiSetting(key=key, value=json.dumps(value)))
                db.commit()
                migrated += len(flat)
                logger.info(f"  Migrated {len(flat)} AI settings from ai_config.json")
            except Exception as e:
                db.rollback()
                logger.error(f"  Failed to migrate ai_config.json: {e}")

        # 3. user_prefs/*.json → user_preferences
        if USER_PREFS_DIR.exists():
            try:
                count = 0
                for pfile in USER_PREFS_DIR.glob("*.json"):
                    username = pfile.stem  # "_global" or "rayce185" etc.
                    data = json.loads(pfile.read_text())
                    for key, value in data.items():
                        existing = db.execute(
                            select(UserPreference).where(
                                UserPreference.username == username,
                                UserPreference.key == key,
                            )
                        ).scalar_one_or_none()
                        if not existing:
                            db.add(UserPreference(
                                username=username, key=key, value=json.dumps(value)
                            ))
                            count += 1
                db.commit()
                migrated += count
                logger.info(f"  Migrated {count} user preferences")
            except Exception as e:
                db.rollback()
                logger.error(f"  Failed to migrate user_prefs: {e}")

    if migrated > 0:
        # Write migration marker
        MIGRATION_MARKER.write_text(f"Migrated {migrated} records")
        logger.info(f"Migration complete: {migrated} total records imported")

        # Archive JSON files (don't delete — belt and suspenders)
        archive_dir = DATA_DIR / "json_archive"
        archive_dir.mkdir(exist_ok=True)
        for f in [SETTINGS_JSON, AI_CONFIG_JSON]:
            if f.exists():
                f.rename(archive_dir / f.name)
        if USER_PREFS_DIR.exists():
            import shutil
            shutil.move(str(USER_PREFS_DIR), str(archive_dir / "user_prefs"))
        logger.info(f"  JSON files archived to {archive_dir}")
