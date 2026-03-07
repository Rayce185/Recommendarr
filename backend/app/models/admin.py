"""SQLAlchemy ORM models — admin entities (notifications, onboarding, plugins, settings, routing, AI config)."""

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
    selected_tmdb_ids: Mapped[Optional[list]] = mapped_column(JSON)
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


# ── App Settings (key/value store — replaces settings.json) ─────

class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── User Preferences (replaces user_prefs/*.json) ───────────────

class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("username", "key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)  # "_global" for defaults
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Routing Rules (replaces in-memory defaults) ──────────────────

class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target: Mapped[str] = mapped_column(String(50), nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    root_folder: Mapped[str] = mapped_column(String(500), nullable=False)
    quality_profile_id: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    series_type: Mapped[str] = mapped_column(String(20), default="standard")
    genre_include: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    genre_require: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    keyword_include: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    company_include: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    language_include: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    is_catchall: Mapped[bool] = mapped_column(Boolean, default=False)


# ── Request Log (tracks library adds) ────────────────────────────

class RequestLog(Base):
    __tablename__ = "request_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    instance: Mapped[Optional[str]] = mapped_column(String(50))
    root_folder: Mapped[Optional[str]] = mapped_column(String(500))
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    status: Mapped[str] = mapped_column(String(20), default="added")  # added, exists, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── AI Config (replaces ai_config.json) ──────────────────────────

class AiSetting(Base):
    __tablename__ = "ai_settings"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



# ── Scheduled Refresh ────────────────────────────────────────────

class RefreshSchedule(Base):
    __tablename__ = "refresh_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    hour: Mapped[int] = mapped_column(Integer, default=4)  # 0-23, local time
    minute: Mapped[int] = mapped_column(Integer, default=0)  # 0-59
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_ms: Mapped[Optional[int]] = mapped_column(Integer)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
