"""Group Night sessions — create, share, and view collaborative picks.

POST /group-night/sessions  — save a group night and get share code
GET  /group-night/sessions/{code} — view a shared session
GET  /group-night/sessions — list your sessions (created or invited)
"""

import json
import logging
import secrets
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.database import get_db
from app.models import GroupNightSession

logger = logging.getLogger(__name__)
router = APIRouter()


def _gen_code(length=6) -> str:
    """Generate a short alphanumeric share code."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class SessionCreateRequest(BaseModel):
    participants: list[str] = Field(..., min_length=2, max_length=50)
    domain: str = "all"
    picks: list[dict] = Field(..., min_length=1, max_length=100)
    title: Optional[str] = Field(None, max_length=200)


class SessionResponse(BaseModel):
    code: str
    creator: str
    participants: list[str]
    domain: str
    picks: list[dict]
    title: Optional[str]
    created_at: str


def _row_to_response(row: GroupNightSession) -> SessionResponse:
    return SessionResponse(
        code=row.code,
        creator=row.creator,
        participants=json.loads(row.participants),
        domain=row.domain,
        picks=json.loads(row.picks),
        title=row.title,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.post("/group-night/sessions")
async def create_session(
    body: SessionCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Save group picks as a shareable session."""
    username = current_user.sub

    # Generate unique code (retry on collision)
    for _ in range(5):
        code = _gen_code()
        with get_db() as db:
            existing = db.execute(
                select(GroupNightSession).where(GroupNightSession.code == code)
            ).scalar_one_or_none()
            if not existing:
                break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique code")

    with get_db() as db:
        session = GroupNightSession(
            code=code,
            creator=username,
            participants=json.dumps(body.participants),
            domain=body.domain,
            picks=json.dumps(body.picks),
            title=body.title,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"Group night session created: {code} by {username}")
        return {"code": code, "url": f"/group-night/{code}"}


@router.get("/group-night/sessions/{code}")
async def get_session(code: str):
    """Retrieve a shared group night session by code. No auth required."""
    with get_db() as db:
        row = db.execute(
            select(GroupNightSession).where(GroupNightSession.code == code)
        ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return _row_to_response(row)


@router.get("/group-night/sessions")
async def list_sessions(
    current_user: TokenPayload = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50),
):
    """List sessions where user is creator or participant."""
    username = current_user.sub
    with get_db() as db:
        rows = db.execute(
            select(GroupNightSession)
            .where(
                or_(
                    GroupNightSession.creator == username,
                    GroupNightSession.participants.contains(f'"{username}"'),
                )
            )
            .order_by(GroupNightSession.created_at.desc())
            .limit(limit)
        ).scalars().all()
    return {"sessions": [_row_to_response(r) for r in rows]}
