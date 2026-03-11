"""Database engine — PostgreSQL (production) or SQLite (dev fallback).

Reads DATABASE_URL from environment:
  - If set: connects to PostgreSQL (psycopg2 sync driver)
  - If unset: falls back to SQLite at DATA_DIR/recommendarr.db
"""

import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "recommendarr.db"
DATABASE_URL = os.getenv("DATABASE_URL", "")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


_engine = None
_session_factory = None
_is_postgres = False


def _sqlite_pragmas(dbapi_conn, connection_record):
    """Enable WAL mode + FK enforcement for SQLite only."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def is_postgres() -> bool:
    """Return True if the active engine targets PostgreSQL."""
    return _is_postgres


def get_engine():
    global _engine, _is_postgres
    if _engine is None:
        if DATABASE_URL:
            _is_postgres = True
            _engine = create_engine(
                DATABASE_URL,
                echo=False,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_recycle=300,
            )
            logger.info("Database engine created: PostgreSQL")
        else:
            _is_postgres = False
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{DB_PATH}"
            _engine = create_engine(url, echo=False, pool_pre_ping=True)
            event.listen(_engine, "connect", _sqlite_pragmas)
            logger.info(f"Database engine created: SQLite ({DB_PATH})")
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            get_engine(), class_=Session, expire_on_commit=False
        )
    return _session_factory


def get_db() -> Session:
    """Get a database session (context manager style)."""
    factory = get_session_factory()
    return factory()


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    engine = get_engine()
    import app.models  # noqa: F401
    Base.metadata.create_all(engine)
    logger.info("Database tables initialized")
