"""SQLAlchemy ORM models — push notification subscriptions."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PushSubscription(Base):
    """Web Push API subscription per user per device.

    Each subscription represents a unique browser/device endpoint.
    The subscription_info JSON contains the PushSubscription object
    from the browser's Push API (endpoint, keys.p256dh, keys.auth).
    """
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "endpoint_hash", name="uq_push_sub_user_endpoint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
