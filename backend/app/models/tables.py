"""SQLAlchemy ORM models — all database tables."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Integer, BigInteger, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, Index, UniqueConstraint, JSON,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    similar_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
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

class VibePlaylist(Base):
    __tablename__ = "vibe_playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    auto_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    pattern_type: Mapped[Optional[str]] = mapped_column(String(50))
    pattern_params: Mapped[Optional[dict]] = mapped_column(JSONB)
    cover_tmdb_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
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
    tmdb_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class UserCollectionProgress(Base):
    __tablename__ = "user_collection_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "collection_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    watched_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
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
    confirmed_tmdb_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
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
    tmdb_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
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


# ── Cultural Pulse / Zeitgeist ───────────────────────────────────

class CulturalEvent(Base):
    __tablename__ = "cultural_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_name: Mapped[str] = mapped_column(String(500), nullable=False)
    event_description: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(30))
    thematic_keywords: Mapped[Optional[dict]] = mapped_column(JSONB)
    thematic_embedding_id: Mapped[Optional[str]] = mapped_column(String(100))
    sensitivity_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CulturalEventRecommendation(Base):
    __tablename__ = "cultural_event_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("cultural_events.id", ondelete="CASCADE"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    thematic_connection: Mapped[Optional[str]] = mapped_column(Text)
    similarity_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CulturalEventDismissal(Base):
    __tablename__ = "cultural_event_dismissals"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("cultural_events.id"))
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PulseSource(Base):
    __tablename__ = "pulse_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(String(200))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(30))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    check_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Zeitgeist Events ─────────────────────────────────────────────

class ZeitgeistEvent(Base):
    __tablename__ = "zeitgeist_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_feed: Mapped[Optional[str]] = mapped_column(String(100))
    region: Mapped[Optional[str]] = mapped_column(String(50))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ZeitgeistMapping(Base):
    __tablename__ = "zeitgeist_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("zeitgeist_events.id", ondelete="CASCADE"))
    mapped_genres: Mapped[Optional[list]] = mapped_column(ARRAY(String(200)))
    mapped_keywords: Mapped[Optional[list]] = mapped_column(ARRAY(String(200)))
    mapped_themes: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    mapped_tmdb_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
    embedding_query: Mapped[Optional[str]] = mapped_column(Text)
    weight_boost: Mapped[float] = mapped_column(Numeric(4, 3), default=0.10)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ZeitgeistDismissal(Base):
    __tablename__ = "zeitgeist_dismissals"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("zeitgeist_events.id"))
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContextualConfig(Base):
    __tablename__ = "contextual_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    enable_temporal: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_weather: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_zeitgeist: Mapped[bool] = mapped_column(Boolean, default=True)
    max_contextual_weight: Mapped[float] = mapped_column(Numeric(4, 3), default=0.20)


class ContextualSignal(Base):
    __tablename__ = "contextual_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    signal_type: Mapped[Optional[str]] = mapped_column(String(30))
    signal_value: Mapped[Optional[str]] = mapped_column(String(200))
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zeitgeist_events.id"))
    weight_applied: Mapped[Optional[float]] = mapped_column(Numeric(4, 3))
    recommendation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recommendation_log.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Wrapped Snapshots ────────────────────────────────────────────

class WrappedSnapshot(Base):
    __tablename__ = "wrapped_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Notifications ────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[Optional[str]] = mapped_column(Text)
    data: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel_type: Mapped[str] = mapped_column(String(30), nullable=False)
    channel_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled_events: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    imported_from: Mapped[Optional[str]] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Onboarding ───────────────────────────────────────────────────

class OnboardingQuiz(Base):
    __tablename__ = "onboarding_quiz"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    selected_tmdb_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer))
    genre_preferences: Mapped[Optional[dict]] = mapped_column(JSONB)
    imported_from: Mapped[Optional[str]] = mapped_column(String(30))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Release Notifications (Coming Soon) ──────────────────────────

class ReleaseNotification(Base):
    __tablename__ = "release_notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "tmdb_id", "media_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    expected_date: Mapped[Optional[date]] = mapped_column(Date)
    source: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Plugins ──────────────────────────────────────────────────────

class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(20))
    author: Mapped[Optional[str]] = mapped_column(String(200))
    interfaces: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONB)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
