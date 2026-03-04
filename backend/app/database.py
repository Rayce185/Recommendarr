"""SQLite database engine — auto-creates on first use, no external deps."""

import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "recommendarr.db"


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


# Synchronous engine for SQLite (no async driver needed — SQLite is single-file)
_engine = None
_session_factory = None


def _sqlite_wal_mode(dbapi_conn, connection_record):
    """Enable WAL mode for better concurrent read performance."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine():
    global _engine
    if _engine is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{DB_PATH}"
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
        event.listen(_engine, "connect", _sqlite_wal_mode)
        logger.info(f"Database engine created: {DB_PATH}")
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(get_engine(), class_=Session, expire_on_commit=False)
    return _session_factory


def get_db() -> Session:
    """Get a database session (context manager style)."""
    factory = get_session_factory()
    return factory()


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    engine = get_engine()
    # Import models so Base.metadata knows about them
    import app.models.tables  # noqa: F401
    Base.metadata.create_all(engine)
    logger.info("Database tables initialized")
