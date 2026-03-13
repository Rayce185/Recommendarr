"""SQLAlchemy ORM models — pulse and zeitgeist entities (cultural events, contextual signals, wrapped)."""

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
    mapped_genres: Mapped[Optional[list]] = mapped_column(JSON)
    mapped_keywords: Mapped[Optional[list]] = mapped_column(JSON)
    mapped_themes: Mapped[Optional[list]] = mapped_column(JSON)
    mapped_tmdb_ids: Mapped[Optional[list]] = mapped_column(JSON)
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

