"""SQLAlchemy ORM models — core entities (users, watch history, TMDB, recommendations, watchlists, playback)."""

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

# ── Users ────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    plex_user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100))
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(300))
    thumb_url: Mapped[Optional[str]] = mapped_column(String(500))
    taste_vector_id: Mapped[Optional[str]] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(10), default="en-US")
    history_depth_months: Mapped[Optional[int]] = mapped_column(Integer, default=12)
    cross_pollination: Mapped[str] = mapped_column(String(20), default="separate")  # separate | blend | custom
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserLibraryAccess(Base):
    __tablename__ = "user_library_access"
    __table_args__ = (
        UniqueConstraint("user_id", "plex_section_key"),
        Index("idx_library_access_user", "user_id", "is_accessible"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plex_section_key: Mapped[int] = mapped_column(Integer, nullable=False)
    plex_sharing_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    library_title: Mapped[Optional[str]] = mapped_column(String(200))
    library_type: Mapped[Optional[str]] = mapped_column(String(10))
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Watch History ────────────────────────────────────────────────

class WatchHistory(Base):
    __tablename__ = "watch_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    plex_rating_key: Mapped[Optional[str]] = mapped_column(String(50))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    total_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    completion_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    watch_count: Mapped[int] = mapped_column(Integer, default=1)
    user_rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 1))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── TMDB Cache ───────────────────────────────────────────────────

class TmdbCache(Base):
    __tablename__ = "tmdb_cache"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "media_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    original_title: Mapped[Optional[str]] = mapped_column(String(500))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    genres: Mapped[Optional[dict]] = mapped_column(JSONB)
    keywords: Mapped[Optional[dict]] = mapped_column(JSONB)
    cast_crew: Mapped[Optional[dict]] = mapped_column(JSONB)
    overview: Mapped[Optional[str]] = mapped_column(Text)
    vote_average: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    popularity: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    poster_path: Mapped[Optional[str]] = mapped_column(String(200))
    backdrop_path: Mapped[Optional[str]] = mapped_column(String(200))
    trailer_key: Mapped[Optional[str]] = mapped_column(String(50))  # YouTube ID
    runtime_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    original_language: Mapped[Optional[str]] = mapped_column(String(10))
    production_countries: Mapped[Optional[dict]] = mapped_column(JSONB)
    similar_ids: Mapped[Optional[list]] = mapped_column(JSON)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Recommendations ──────────────────────────────────────────────

class RecommendationLog(Base):
    __tablename__ = "recommendation_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(10))
    mode: Mapped[Optional[str]] = mapped_column(String(20))
    score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    signals: Mapped[Optional[dict]] = mapped_column(JSONB)
    influenced_by: Mapped[Optional[dict]] = mapped_column(JSONB)
    was_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    was_watched: Mapped[bool] = mapped_column(Boolean, default=False)
    was_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str] = mapped_column(String(10))  # up | down | dismiss
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Watchlists ───────────────────────────────────────────────────

class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    color: Mapped[Optional[str]] = mapped_column(String(7))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "tmdb_id", "media_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ── Influence Overrides ──────────────────────────────────────────

class InfluenceOverride(Base):
    __tablename__ = "influence_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "influence_type", "influence_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    influence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    influence_key: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # boost | suppress | block
    weight_modifier: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Playback Sessions ────────────────────────────────────────────

class PlaybackSession(Base):
    __tablename__ = "playback_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[Optional[str]] = mapped_column(String(200))
    device_name: Mapped[Optional[str]] = mapped_column(String(200))
    plex_key: Mapped[Optional[str]] = mapped_column(String(100))
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source: Mapped[Optional[str]] = mapped_column(String(20))
    recommendation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recommendation_log.id"))


# ── Auto-Grab ────────────────────────────────────────────────────

class AutoGrabConfig(Base):
    __tablename__ = "auto_grab_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_threshold: Mapped[float] = mapped_column(Numeric(3, 2), default=0.85)
    scope: Mapped[str] = mapped_column(String(20), default="movies")
    daily_limit: Mapped[int] = mapped_column(Integer, default=3)
    notify_on_grab: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutoGrabLog(Base):
    __tablename__ = "auto_grab_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    triggered_by_users: Mapped[Optional[int]] = mapped_column(Integer)
    avg_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    radarr_id: Mapped[Optional[int]] = mapped_column(Integer)
    grabbed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ── Availability Alerts ──────────────────────────────────────────

class AvailabilityAlert(Base):
    __tablename__ = "availability_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    source_recommendation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recommendation_log.id"))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ── Vibe Playlists ───────────────────────────────────────────────

