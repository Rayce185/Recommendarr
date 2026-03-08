"""Friend system — request, accept, decline, remove, list.

Uses the Friendship model from features.py with status values:
  pending  — request sent, awaiting response
  accepted — mutual friendship
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import select, or_, and_
from app.database import get_db
from app.models import Friendship, PrivacySettings, User

logger = logging.getLogger(__name__)


def _resolve_user_id(db, username: str) -> int | None:
    """Look up user ID from username."""
    row = db.execute(
        select(User.id).where(User.username == username)
    ).scalar_one_or_none()
    return row


def _get_privacy(db, user_id: int) -> PrivacySettings | None:
    """Get privacy settings for a user, or None for defaults."""
    return db.execute(
        select(PrivacySettings).where(PrivacySettings.user_id == user_id)
    ).scalar_one_or_none()


def send_friend_request(from_username: str, to_username: str) -> dict:
    """Send a friend request. Returns status dict."""
    with get_db() as db:
        from_id = _resolve_user_id(db, from_username)
        to_id = _resolve_user_id(db, to_username)

        if not from_id or not to_id:
            return {"ok": False, "error": "User not found"}
        if from_id == to_id:
            return {"ok": False, "error": "Cannot friend yourself"}

        # Check privacy settings
        privacy = _get_privacy(db, to_id)
        if privacy and not privacy.allow_friend_requests:
            return {"ok": False, "error": "User has disabled friend requests"}

        # Check for existing relationship (either direction)
        existing = db.execute(select(Friendship).where(
            or_(
                and_(Friendship.user_id == from_id, Friendship.friend_user_id == to_id),
                and_(Friendship.user_id == to_id, Friendship.friend_user_id == from_id),
            )
        )).scalar_one_or_none()

        if existing:
            if existing.status == "accepted":
                return {"ok": False, "error": "Already friends"}
            if existing.status == "pending":
                # If the other person already sent us a request, auto-accept
                if existing.user_id == to_id:
                    existing.status = "accepted"
                    existing.accepted_at = datetime.now(timezone.utc)
                    db.commit()
                    return {"ok": True, "status": "accepted", "auto": True}
                return {"ok": False, "error": "Request already pending"}

        friendship = Friendship(
            user_id=from_id,
            friend_user_id=to_id,
            status="pending",
        )
        db.add(friendship)
        db.commit()
        return {"ok": True, "status": "pending"}


def respond_to_request(username: str, from_username: str, accept: bool) -> dict:
    """Accept or decline a pending friend request."""
    with get_db() as db:
        my_id = _resolve_user_id(db, username)
        their_id = _resolve_user_id(db, from_username)
        if not my_id or not their_id:
            return {"ok": False, "error": "User not found"}

        row = db.execute(select(Friendship).where(
            Friendship.user_id == their_id,
            Friendship.friend_user_id == my_id,
            Friendship.status == "pending",
        )).scalar_one_or_none()

        if not row:
            return {"ok": False, "error": "No pending request from this user"}

        if accept:
            row.status = "accepted"
            row.accepted_at = datetime.now(timezone.utc)
            db.commit()
            return {"ok": True, "status": "accepted"}
        else:
            db.delete(row)
            db.commit()
            return {"ok": True, "status": "declined"}


def remove_friend(username: str, friend_username: str) -> dict:
    """Remove a friendship (either direction)."""
    with get_db() as db:
        my_id = _resolve_user_id(db, username)
        their_id = _resolve_user_id(db, friend_username)
        if not my_id or not their_id:
            return {"ok": False, "error": "User not found"}

        row = db.execute(select(Friendship).where(
            or_(
                and_(Friendship.user_id == my_id, Friendship.friend_user_id == their_id),
                and_(Friendship.user_id == their_id, Friendship.friend_user_id == my_id),
            )
        )).scalar_one_or_none()

        if not row:
            return {"ok": False, "error": "Not friends"}

        db.delete(row)
        db.commit()
        return {"ok": True}


def get_friends(username: str) -> list[dict]:
    """Get accepted friends for a user."""
    with get_db() as db:
        my_id = _resolve_user_id(db, username)
        if not my_id:
            return []

        rows = db.execute(select(Friendship).where(
            or_(
                and_(Friendship.user_id == my_id, Friendship.status == "accepted"),
                and_(Friendship.friend_user_id == my_id, Friendship.status == "accepted"),
            )
        )).scalars().all()

        friend_ids = []
        for r in rows:
            fid = r.friend_user_id if r.user_id == my_id else r.user_id
            friend_ids.append((fid, r.accepted_at))

        if not friend_ids:
            return []

        users = {u.id: u for u in db.execute(
            select(User).where(User.id.in_([f[0] for f in friend_ids]))
        ).scalars().all()}

        return [
            {
                "username": users[fid].username,
                "display_name": users[fid].display_name or users[fid].username,
                "thumb": users[fid].thumb_url or "",
                "since": acc.isoformat() if acc else None,
            }
            for fid, acc in friend_ids if fid in users
        ]


def get_pending_requests(username: str) -> dict:
    """Get incoming and outgoing pending requests."""
    with get_db() as db:
        my_id = _resolve_user_id(db, username)
        if not my_id:
            return {"incoming": [], "outgoing": []}

        incoming = db.execute(select(Friendship).where(
            Friendship.friend_user_id == my_id,
            Friendship.status == "pending",
        )).scalars().all()

        outgoing = db.execute(select(Friendship).where(
            Friendship.user_id == my_id,
            Friendship.status == "pending",
        )).scalars().all()

        # Resolve usernames
        all_ids = [r.user_id for r in incoming] + [r.friend_user_id for r in outgoing]
        users = {}
        if all_ids:
            users = {u.id: u for u in db.execute(
                select(User).where(User.id.in_(all_ids))
            ).scalars().all()}

        return {
            "incoming": [
                {
                    "username": users[r.user_id].username,
                    "display_name": users[r.user_id].display_name or users[r.user_id].username,
                    "thumb": users[r.user_id].thumb_url or "",
                    "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                }
                for r in incoming if r.user_id in users
            ],
            "outgoing": [
                {
                    "username": users[r.friend_user_id].username,
                    "display_name": users[r.friend_user_id].display_name or users[r.friend_user_id].username,
                    "thumb": users[r.friend_user_id].thumb_url or "",
                    "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                }
                for r in outgoing if r.friend_user_id in users
            ],
        }


def get_privacy_settings(username: str) -> dict:
    """Get privacy settings for a user (with defaults)."""
    defaults = {
        "show_activity_to_friends": True,
        "anonymize_activity": False,
        "contribute_to_collaborative": True,
        "show_in_server_stats": True,
        "allow_friend_requests": True,
    }
    with get_db() as db:
        uid = _resolve_user_id(db, username)
        if not uid:
            return defaults
        ps = _get_privacy(db, uid)
        if not ps:
            return defaults
        return {
            "show_activity_to_friends": ps.show_activity_to_friends,
            "anonymize_activity": ps.anonymize_activity,
            "contribute_to_collaborative": ps.contribute_to_collaborative,
            "show_in_server_stats": ps.show_in_server_stats,
            "allow_friend_requests": ps.allow_friend_requests,
        }


def update_privacy_settings(username: str, updates: dict) -> dict:
    """Update privacy settings for a user."""
    allowed = {
        "show_activity_to_friends", "anonymize_activity",
        "contribute_to_collaborative", "show_in_server_stats",
        "allow_friend_requests",
    }
    with get_db() as db:
        uid = _resolve_user_id(db, username)
        if not uid:
            return {"ok": False, "error": "User not found"}

        ps = _get_privacy(db, uid)
        if not ps:
            ps = PrivacySettings(user_id=uid)
            db.add(ps)

        for key, val in updates.items():
            if key in allowed and isinstance(val, bool):
                setattr(ps, key, val)

        db.commit()
        return {"ok": True, "settings": get_privacy_settings(username)}
