"""SQLAlchemy models — Kick-Vote / Library Pruning system.

Four tables: vitality_scores, sunset_items, sunset_votes, kicked_items.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, Index, UniqueConstraint, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class VitalityScore(Base):
    """Daily snapshot of a library item's health score."""
    __tablename__ = "vitality_scores"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "media_type", name="uq_vitality_item"),
        Index("idx_vitality_zone", "zone"),
        Index("idx_vitality_score", "composite_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    servarr_id: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    poster_path: Mapped[Optional[str]] = mapped_column(String(200))

    # Composite + individual signals (0-100 each)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    recency_score: Mapped[float] = mapped_column(Float, default=0.0)
    velocity_score: Mapped[float] = mapped_column(Float, default=0.0)
    breadth_score: Mapped[float] = mapped_column(Float, default=0.0)
    rec_frequency_score: Mapped[float] = mapped_column(Float, default=0.0)
    niche_score: Mapped[float] = mapped_column(Float, default=0.0)

    zone: Mapped[str] = mapped_column(String(20), default="healthy")
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SunsetItem(Base):
    """State machine for items in the sunset voting pipeline."""
    __tablename__ = "sunset_items"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "media_type", name="uq_sunset_item"),
        Index("idx_sunset_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    servarr_id: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    poster_path: Mapped[Optional[str]] = mapped_column(String(200))

    entered_sunset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    grace_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # voting | pending_admin | approved | kicked | reprieved
    status: Mapped[str] = mapped_column(String(20), default="voting")
    votes_keep: Mapped[int] = mapped_column(Integer, default=0)
    votes_kick: Mapped[int] = mapped_column(Integer, default=0)
    kick_method: Mapped[Optional[str]] = mapped_column(String(20))
    immune_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class SunsetVote(Base):
    """Per-user vote on a sunset zone item."""
    __tablename__ = "sunset_votes"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "media_type", "user_id", name="uq_sunset_vote"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    vote: Mapped[str] = mapped_column(String(10), nullable=False)  # keep | kick
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KickedItem(Base):
    """Metadata snapshot of removed items for one-click re-download."""
    __tablename__ = "kicked_items"
    __table_args__ = (
        Index("idx_kicked_tmdb", "tmdb_id", "media_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    servarr_id: Mapped[int] = mapped_column(Integer, nullable=False)
    servarr_type: Mapped[str] = mapped_column(String(10), nullable=False)  # radarr | sonarr
    quality_profile_id: Mapped[Optional[int]] = mapped_column(Integer)
    quality_profile_name: Mapped[Optional[str]] = mapped_column(String(100))
    root_folder: Mapped[Optional[str]] = mapped_column(String(500))
    tags: Mapped[Optional[dict]] = mapped_column(JSON)
    poster_path: Mapped[Optional[str]] = mapped_column(String(200))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    genres: Mapped[Optional[dict]] = mapped_column(JSON)
    overview: Mapped[Optional[str]] = mapped_column(Text)
    vitality_at_kick: Mapped[Optional[float]] = mapped_column(Float)

    kicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    kicked_by: Mapped[str] = mapped_column(String(20), nullable=False)  # auto | vote | admin
    redownloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    redownload_eta_tier: Mapped[Optional[str]] = mapped_column(String(20))
