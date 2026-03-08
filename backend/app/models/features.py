"""SQLAlchemy ORM models — feature entities (vibes, collections, social, imports, discovery, regional)."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Integer, BigInteger, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, Index, UniqueConstraint, JSON,
)
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

class VibePlaylist(Base):
    __tablename__ = "vibe_playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    auto_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    pattern_type: Mapped[Optional[str]] = mapped_column(String(50))
    pattern_params: Mapped[Optional[dict]] = mapped_column(JSONB)
    cover_tmdb_ids: Mapped[Optional[list]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VibePlaylistItem(Base):
    __tablename__ = "vibe_playlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    vibe_id: Mapped[int] = mapped_column(ForeignKey("vibe_playlists.id", ondelete="CASCADE"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    position: Mapped[Optional[int]] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Collections ──────────────────────────────────────────────────

class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("collection_type", "collection_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    collection_key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(500))
    total_items: Mapped[Optional[int]] = mapped_column(Integer)
    tmdb_ids: Mapped[Optional[list]] = mapped_column(JSON)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class UserCollectionProgress(Base):
    __tablename__ = "user_collection_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "collection_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    watched_ids: Mapped[Optional[list]] = mapped_column(JSON)
    completion_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Social ───────────────────────────────────────────────────────

class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_id", "friend_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    friend_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PrivacySettings(Base):
    __tablename__ = "privacy_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    show_activity_to_friends: Mapped[bool] = mapped_column(Boolean, default=True)
    anonymize_activity: Mapped[bool] = mapped_column(Boolean, default=False)
    contribute_to_collaborative: Mapped[bool] = mapped_column(Boolean, default=True)
    show_in_server_stats: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_friend_requests: Mapped[bool] = mapped_column(Boolean, default=True)


# ── Import Jobs ──────────────────────────────────────────────────

class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    extracted_titles: Mapped[Optional[dict]] = mapped_column(JSONB)
    confirmed_tmdb_ids: Mapped[Optional[list]] = mapped_column(JSON)
    added_to_radarr: Mapped[int] = mapped_column(Integer, default=0)
    added_to_watchlist: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DiscoveryCache(Base):
    __tablename__ = "discovery_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(5))
    title: Mapped[Optional[str]] = mapped_column(String(200))
    tmdb_ids: Mapped[Optional[list]] = mapped_column(JSON)
    item_count: Mapped[Optional[int]] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ── World Cinema Map ─────────────────────────────────────────────

class RegionalTrending(Base):
    __tablename__ = "regional_trending"
    __table_args__ = (
        UniqueConstraint("country_code", "tmdb_id", "period_type", "period_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(String(5), nullable=False)
    country_name: Mapped[Optional[str]] = mapped_column(String(100))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    position: Mapped[Optional[int]] = mapped_column(Integer)
    period_type: Mapped[Optional[str]] = mapped_column(String(10))
    period_date: Mapped[Optional[date]] = mapped_column(Date)
    in_library: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class GroupNightSession(Base):
    """Shareable group night recommendation session."""
    __tablename__ = "group_night_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    creator: Mapped[str] = mapped_column(String(200), nullable=False)
    participants: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    domain: Mapped[str] = mapped_column(String(20), default="all")
    picks: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    title: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
