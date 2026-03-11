"""Sunset manager — vote flow state machine for library pruning.

Handles zone transitions, vote casting/tallying, grace period management,
and resolution (auto-kick for dead zone, admin confirm for borderline).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.core import User
from app.models.library_health import VitalityScore, SunsetItem, SunsetVote
from app.services.vitality_scoring import DEFAULT_THRESHOLDS

logger = logging.getLogger(__name__)


def process_zone_transitions(
    db: Session, thresholds: dict | None = None,
) -> dict:
    """Process all zone transitions after a vitality recalculation.

    1. Items that dropped into sunset → create SunsetItem if not exists
    2. Items that recovered to healthy → reprieve if in voting
    3. Items in dead zone → mark for auto-kick
    4. Grace-expired items → resolve votes

    Returns transition summary.
    """
    t = thresholds or DEFAULT_THRESHOLDS
    now = datetime.now(timezone.utc)
    grace_days = int(t.get("grace_period_days", 7))
    summary = {"entered_sunset": 0, "recovered": 0, "auto_dead": 0, "vote_resolved": 0}

    # All current vitality scores
    scores = db.execute(select(VitalityScore)).scalars().all()

    # Current sunset items (active = voting or pending_admin)
    active_sunsets = {
        (s.tmdb_id, s.media_type): s
        for s in db.execute(
            select(SunsetItem).where(SunsetItem.status.in_(["voting", "pending_admin"]))
        ).scalars().all()
    }

    # ALL sunset items regardless of status — prevents duplicate inserts
    all_sunset_keys = {
        (r.tmdb_id, r.media_type)
        for r in db.execute(
            select(SunsetItem.tmdb_id, SunsetItem.media_type)
        ).all()
    }

    for vs in scores:
        key = (vs.tmdb_id, vs.media_type)
        existing = active_sunsets.get(key)

        if vs.zone == "healthy":
            # If item was in sunset, reprieve it
            if existing and existing.status == "voting":
                existing.status = "reprieved"
                existing.resolved_at = now
                existing.immune_until = now + timedelta(
                    days=int(t.get("reprieve_immunity_days", 30))
                )
                summary["recovered"] += 1
                logger.info("Reprieved (recovered): %s [%s]", vs.title, vs.tmdb_id)

        elif vs.zone == "sunset":
            if not existing and key not in all_sunset_keys:
                # Check immunity
                prev = db.execute(
                    select(SunsetItem).where(
                        SunsetItem.tmdb_id == vs.tmdb_id,
                        SunsetItem.media_type == vs.media_type,
                        SunsetItem.status == "reprieved",
                        SunsetItem.immune_until > now,
                    )
                ).scalar_one_or_none()
                if prev:
                    continue  # still immune

                sunset = SunsetItem(
                    tmdb_id=vs.tmdb_id, media_type=vs.media_type,
                    servarr_id=vs.servarr_id, title=vs.title,
                    poster_path=vs.poster_path,
                    entered_sunset_at=now,
                    grace_expires_at=now + timedelta(days=grace_days),
                    status="voting",
                )
                db.add(sunset)
                summary["entered_sunset"] += 1
                logger.info("Entered sunset: %s [%s] score=%.1f",
                            vs.title, vs.tmdb_id, vs.composite_score)

        elif vs.zone == "dead":
            if existing and existing.status == "voting":
                existing.status = "approved"
                existing.kick_method = "auto"
                existing.resolved_at = now
                summary["auto_dead"] += 1
                logger.info("Auto-approved (dead zone): %s [%s] score=%.1f",
                            vs.title, vs.tmdb_id, vs.composite_score)
            elif not existing and key not in all_sunset_keys:
                # Dead item not yet in pipeline — fast-track
                sunset = SunsetItem(
                    tmdb_id=vs.tmdb_id, media_type=vs.media_type,
                    servarr_id=vs.servarr_id, title=vs.title,
                    poster_path=vs.poster_path,
                    entered_sunset_at=now,
                    grace_expires_at=now,  # no grace for dead items
                    status="approved", kick_method="auto",
                    resolved_at=now,
                )
                db.add(sunset)
                summary["auto_dead"] += 1

    # Resolve grace-expired voting items
    expired = db.execute(
        select(SunsetItem).where(
            SunsetItem.status == "voting",
            SunsetItem.grace_expires_at <= now,
        )
    ).scalars().all()

    for item in expired:
        result = _resolve_votes(db, item, t)
        summary["vote_resolved"] += 1
        logger.info("Vote resolved: %s [%s] → %s", item.title, item.tmdb_id, result)

    db.commit()
    return summary


def _resolve_votes(db: Session, item: SunsetItem, thresholds: dict) -> str:
    """Resolve a grace-expired sunset item based on vote tally.

    Returns new status string.
    """
    kick_pct = float(thresholds.get("vote_kick_pct", 0.60))
    quorum = int(thresholds.get("vote_quorum", 3))
    now = datetime.now(timezone.utc)

    total_votes = item.votes_keep + item.votes_kick

    if total_votes < quorum:
        # Not enough votes — extend grace by 3 more days
        item.grace_expires_at = now + timedelta(days=3)
        logger.info("Quorum not met for %s (%d/%d) — extending grace",
                     item.title, total_votes, quorum)
        return "extended"

    kick_ratio = item.votes_kick / total_votes if total_votes > 0 else 0

    if kick_ratio >= kick_pct:
        item.status = "pending_admin"
        item.kick_method = "vote"
        return "pending_admin"
    else:
        item.status = "reprieved"
        item.resolved_at = now
        item.immune_until = now + timedelta(
            days=int(thresholds.get("reprieve_immunity_days", 30))
        )
        return "reprieved"


def cast_vote(
    tmdb_id: int, media_type: str, plex_user_id: int, vote: str,
) -> dict:
    """Cast or update a user's vote on a sunset item.

    Returns vote status dict.
    """
    if vote not in ("keep", "kick"):
        raise ValueError(f"Invalid vote: {vote}")

    db = get_db()
    try:
        # Resolve plex_user_id to internal user.id (FK target)
        user_row = db.execute(
            select(User).where(User.plex_user_id == plex_user_id)
        ).scalar_one_or_none()
        if not user_row:
            raise ValueError("User not found")
        user_id = user_row.id

        # Verify item is in voting state
        item = db.execute(
            select(SunsetItem).where(
                SunsetItem.tmdb_id == tmdb_id,
                SunsetItem.media_type == media_type,
                SunsetItem.status == "voting",
            )
        ).scalar_one_or_none()

        if not item:
            raise ValueError("Item is not in active voting")

        # Upsert vote
        existing_vote = db.execute(
            select(SunsetVote).where(
                SunsetVote.tmdb_id == tmdb_id,
                SunsetVote.media_type == media_type,
                SunsetVote.user_id == user_id,
            )
        ).scalar_one_or_none()

        old_vote = None
        if existing_vote:
            old_vote = existing_vote.vote
            existing_vote.vote = vote
            existing_vote.voted_at = datetime.now(timezone.utc)
        else:
            db.add(SunsetVote(
                tmdb_id=tmdb_id, media_type=media_type,
                user_id=user_id, vote=vote,
            ))

        # Update cached tallies
        _refresh_vote_tallies(db, item)

        db.commit()

        return {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "vote": vote,
            "previous_vote": old_vote,
            "votes_keep": item.votes_keep,
            "votes_kick": item.votes_kick,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _refresh_vote_tallies(db: Session, item: SunsetItem):
    """Recalculate cached vote counts from actual votes."""
    from sqlalchemy import func as sqlfunc
    rows = db.execute(
        select(SunsetVote.vote, sqlfunc.count(SunsetVote.id))
        .where(
            SunsetVote.tmdb_id == item.tmdb_id,
            SunsetVote.media_type == item.media_type,
        )
        .group_by(SunsetVote.vote)
    ).all()
    tallies = {r[0]: r[1] for r in rows}
    item.votes_keep = tallies.get("keep", 0)
    item.votes_kick = tallies.get("kick", 0)


def admin_confirm_kick(tmdb_id: int, media_type: str) -> SunsetItem:
    """Admin confirms a pending kick. Returns updated item."""
    db = get_db()
    try:
        item = db.execute(
            select(SunsetItem).where(
                SunsetItem.tmdb_id == tmdb_id,
                SunsetItem.media_type == media_type,
                SunsetItem.status == "pending_admin",
            )
        ).scalar_one_or_none()
        if not item:
            raise ValueError("No pending kick for this item")

        item.status = "approved"
        item.resolved_at = datetime.now(timezone.utc)
        db.commit()
        return item
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def admin_veto_kick(tmdb_id: int, media_type: str) -> SunsetItem:
    """Admin vetoes a pending kick → reprieve with immunity."""
    db = get_db()
    try:
        item = db.execute(
            select(SunsetItem).where(
                SunsetItem.tmdb_id == tmdb_id,
                SunsetItem.media_type == media_type,
                SunsetItem.status == "pending_admin",
            )
        ).scalar_one_or_none()
        if not item:
            raise ValueError("No pending kick for this item")

        now = datetime.now(timezone.utc)
        item.status = "reprieved"
        item.resolved_at = now
        item.immune_until = now + timedelta(days=30)
        db.commit()
        return item
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
