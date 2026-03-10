"""Web Push notification service — VAPID key management + push delivery.

Handles VAPID key generation/persistence, subscription CRUD, and sending
push notifications via the Web Push protocol (RFC 8030/8291/8292).
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from sqlalchemy import select, delete

from app.database import get_db
from app.models.push import PushSubscription

logger = logging.getLogger(__name__)

# ── VAPID Key Management ─────────────────────────────────────────

_vapid_cache: dict = {}


def _get_settings_store():
    from app.services.settings_store import get_settings_store
    return get_settings_store()


def get_vapid_keys() -> dict:
    """Get or generate VAPID keys. Keys persist in settings store."""
    if _vapid_cache.get("private"):
        return _vapid_cache

    store = _get_settings_store()
    private_key = store.get("vapid_private_key")
    public_key = store.get("vapid_public_key")

    if private_key and public_key:
        _vapid_cache["private"] = private_key
        _vapid_cache["public"] = public_key
        return _vapid_cache

    # Generate new VAPID key pair
    vapid = Vapid()
    vapid.generate_keys()
    private_key = vapid.private_pem().decode("utf-8")
    raw_pub = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_key = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode("ascii")

    store.set("vapid_private_key", private_key)
    store.set("vapid_public_key", public_key)
    logger.info("Generated new VAPID key pair")

    _vapid_cache["private"] = private_key
    _vapid_cache["public"] = public_key
    return _vapid_cache


def get_vapid_public_key() -> str:
    """Return the URL-safe base64 VAPID public key for frontend."""
    return get_vapid_keys()["public"]


# ── Subscription Management ──────────────────────────────────────

def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def subscribe(
    user_id: int, endpoint: str, p256dh: str, auth: str,
    user_agent: Optional[str] = None,
) -> PushSubscription:
    """Register or update a push subscription for a user+device."""
    db = get_db()
    try:
        eh = _endpoint_hash(endpoint)
        existing = db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint_hash == eh,
            )
        ).scalar_one_or_none()

        if existing:
            existing.endpoint = endpoint
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = user_agent
            existing.last_used_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("Updated push subscription for user %d", user_id)
            return existing

        sub = PushSubscription(
            user_id=user_id, endpoint=endpoint, endpoint_hash=eh,
            p256dh=p256dh, auth=auth, user_agent=user_agent,
        )
        db.add(sub)
        db.commit()
        logger.info("Created push subscription for user %d", user_id)
        return sub
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def unsubscribe(user_id: int, endpoint: str) -> bool:
    """Remove a push subscription."""
    db = get_db()
    try:
        eh = _endpoint_hash(endpoint)
        result = db.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint_hash == eh,
            )
        )
        db.commit()
        removed = result.rowcount > 0
        if removed:
            logger.info("Removed push subscription for user %d", user_id)
        return removed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_user_subscriptions(user_id: int) -> list[PushSubscription]:
    """Get all active push subscriptions for a user."""
    db = get_db()
    try:
        return db.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        ).scalars().all()
    finally:
        db.close()


# ── Push Delivery ────────────────────────────────────────────────

def send_push(user_id: int, title: str, body: str, **kwargs) -> dict:
    """Send a push notification to all subscriptions for a user.

    kwargs: icon, badge, url, tag, data (all optional).
    Returns summary of delivery results.
    """
    subs = get_user_subscriptions(user_id)
    if not subs:
        return {"sent": 0, "failed": 0, "no_subscriptions": True}

    keys = get_vapid_keys()
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": kwargs.get("icon", "/icon-192.png"),
        "badge": kwargs.get("badge", "/icon-192.png"),
        "url": kwargs.get("url", "/"),
        "tag": kwargs.get("tag"),
        "data": kwargs.get("data", {}),
    })

    sent = 0
    failed = 0
    stale_ids = []

    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=keys["private"],
                vapid_claims={"sub": "mailto:push@recommendarr.app"},
            )
            sent += 1
            # Update last_used_at
            db = get_db()
            try:
                sub.last_used_at = datetime.now(timezone.utc)
                db.commit()
            finally:
                db.close()
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                # Subscription expired/invalid — mark for cleanup
                stale_ids.append(sub.id)
                logger.info("Stale push subscription %d (HTTP %d)",
                            sub.id, e.response.status_code)
            else:
                logger.warning("Push delivery failed for sub %d: %s", sub.id, e)
            failed += 1

    # Clean up stale subscriptions
    if stale_ids:
        db = get_db()
        try:
            db.execute(
                delete(PushSubscription).where(PushSubscription.id.in_(stale_ids))
            )
            db.commit()
            logger.info("Cleaned %d stale push subscriptions", len(stale_ids))
        except Exception:
            db.rollback()
        finally:
            db.close()

    return {"sent": sent, "failed": failed, "cleaned": len(stale_ids)}


def send_push_to_all(title: str, body: str, **kwargs) -> dict:
    """Broadcast a push notification to ALL subscribed users."""
    db = get_db()
    try:
        user_ids = [
            r[0] for r in db.execute(
                select(PushSubscription.user_id).distinct()
            ).all()
        ]
    finally:
        db.close()

    total_sent = 0
    total_failed = 0
    for uid in user_ids:
        result = send_push(uid, title, body, **kwargs)
        total_sent += result["sent"]
        total_failed += result["failed"]

    return {"users": len(user_ids), "sent": total_sent, "failed": total_failed}
