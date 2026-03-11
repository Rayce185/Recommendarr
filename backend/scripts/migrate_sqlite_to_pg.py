#!/usr/bin/env python3
"""One-time migration: SQLite → PostgreSQL.

Reads all data from the SQLite database and inserts it into PostgreSQL.
Requires DATABASE_URL env var pointing to PG and DATA_DIR pointing to
the directory containing recommendarr.db.

Usage:
  DATABASE_URL=postgresql://... DATA_DIR=/app/data python scripts/migrate_sqlite_to_pg.py
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

# Add parent dir for app imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
SQLITE_PATH = DATA_DIR / "recommendarr.db"
PG_URL = os.environ.get("DATABASE_URL", "")

# Tables to skip (PG-only or empty/irrelevant)
SKIP_TABLES = {"alembic_version"}


def get_sqlite_tables(sqlite_conn) -> list[str]:
    """Get all table names from SQLite."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_columns(sqlite_conn, table: str) -> list[str]:
    """Get column names for a SQLite table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def migrate():
    if not PG_URL:
        logger.error("DATABASE_URL not set — cannot connect to PostgreSQL")
        sys.exit(1)

    if not SQLITE_PATH.exists():
        logger.error(f"SQLite database not found: {SQLITE_PATH}")
        sys.exit(1)

    logger.info(f"Source: {SQLITE_PATH}")
    logger.info(f"Target: {PG_URL.split('@')[1] if '@' in PG_URL else PG_URL}")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_conn.row_factory = sqlite3.Row

    # Connect to PostgreSQL — import models to create tables
    pg_engine = create_engine(PG_URL, echo=False)

    # Create all tables in PG
    import app.models  # noqa: F401
    from app.database import Base
    Base.metadata.create_all(pg_engine)
    logger.info("PostgreSQL tables created/verified")

    pg_session_factory = sessionmaker(pg_engine)

    # Get PG table list for validation
    pg_inspector = inspect(pg_engine)
    pg_tables = set(pg_inspector.get_table_names())

    # Disable FK constraints for migration (alphabetical order vs FK deps)
    with pg_engine.connect() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        conn.commit()
    logger.info("FK constraints disabled for migration")

    sqlite_tables = get_sqlite_tables(sqlite_conn)
    logger.info(f"Found {len(sqlite_tables)} SQLite tables")

    total_rows = 0

    for table in sorted(sqlite_tables):
        if table in SKIP_TABLES:
            logger.info(f"  SKIP {table}")
            continue

        if table not in pg_tables:
            logger.warning(f"  SKIP {table} — not in PG schema")
            continue

        # Get row count
        count = sqlite_conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        if count == 0:
            logger.info(f"  {table}: 0 rows (skip)")
            continue

        # Get columns that exist in both SQLite and PG
        sqlite_cols = get_table_columns(sqlite_conn, table)
        pg_cols = {c["name"] for c in pg_inspector.get_columns(table)}
        common_cols = [c for c in sqlite_cols if c in pg_cols]

        if not common_cols:
            logger.warning(f"  SKIP {table} — no common columns")
            continue

        # Detect boolean columns in PG for SQLite int→bool coercion
        bool_cols = set()
        for col_info in pg_inspector.get_columns(table):
            if col_info["name"] in common_cols and str(col_info["type"]) == "BOOLEAN":
                bool_cols.add(col_info["name"])

        # Read all rows
        col_list = ", ".join(f"[{c}]" for c in common_cols)
        rows = sqlite_conn.execute(f"SELECT {col_list} FROM [{table}]").fetchall()

        # Batch insert into PG
        with pg_session_factory() as session:
            try:
                # Clear existing data (idempotent re-runs)
                session.execute(text(f'DELETE FROM "{table}"'))

                # Insert in batches of 500
                pg_col_list = ", ".join(f'"{c}"' for c in common_cols)
                placeholders = ", ".join(f":{c}" for c in common_cols)
                insert_sql = text(
                    f'INSERT INTO "{table}" ({pg_col_list}) VALUES ({placeholders})'
                )

                batch = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(common_cols):
                        val = row[i]
                        # Convert SQLite JSON strings to actual dicts for JSONB columns
                        if isinstance(val, str) and val.startswith(("{", "[")):
                            try:
                                val = json.loads(val)
                                val = json.dumps(val)  # Re-serialize for PG text binding
                            except json.JSONDecodeError:
                                pass
                        # Coerce SQLite integer booleans (0/1) to Python bool
                        if col in bool_cols and isinstance(val, int):
                            val = bool(val)
                        row_dict[col] = val
                    batch.append(row_dict)

                    if len(batch) >= 500:
                        session.execute(insert_sql, batch)
                        batch = []

                if batch:
                    session.execute(insert_sql, batch)

                session.commit()
                total_rows += count
                logger.info(f"  {table}: {count} rows migrated")

            except Exception as e:
                session.rollback()
                logger.error(f"  {table}: FAILED — {e}")

    # Re-enable FK constraints
    with pg_engine.connect() as conn:
        conn.execute(text("SET session_replication_role = 'origin'"))
        conn.commit()
    logger.info("FK constraints re-enabled")

    # Reset PG sequences to max(id) + 1
    with pg_session_factory() as session:
        for table in pg_tables:
            try:
                result = session.execute(text(
                    f"SELECT column_default FROM information_schema.columns "
                    f"WHERE table_name = '{table}' AND column_name = 'id'"
                )).fetchone()
                if result and result[0] and "nextval" in str(result[0]):
                    seq_name = str(result[0]).split("'")[1]
                    max_id = session.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')).scalar()
                    if max_id > 0:
                        session.execute(text(f"SELECT setval('{seq_name}', {max_id})"))
                        logger.info(f"  Reset sequence {seq_name} to {max_id}")
            except Exception:
                pass
        session.commit()

    sqlite_conn.close()
    logger.info(f"\nMigration complete: {total_rows} total rows transferred")


if __name__ == "__main__":
    migrate()
