"""Auth API — Plex OAuth login, aligned with Overseerr's flow.

Frontend handles PIN creation and polling directly with plex.tv.
Backend receives the authToken and validates it.

Endpoints:
  POST /auth/plex   — Receive authToken from frontend, validate, return JWT
  GET  /auth/me     — Return current user from JWT (session hydration)
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth.plex_oauth import get_plex_user, check_server_access
from app.auth.jwt_handler import create_token, TokenPayload, get_current_user
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class PlexAuthRequest(BaseModel):
    authToken: str


@router.post("/plex")
async def auth_plex(body: PlexAuthRequest):
    """Authenticate with a Plex auth token (from frontend OAuth flow).

    Same pattern as Overseerr's POST /auth/plex:
    1. Frontend completes PIN flow directly with plex.tv
    2. Frontend sends the resulting authToken here
    3. Backend validates token, checks server access, returns JWT
    """
    if not body.authToken:
        raise HTTPException(status_code=400, detail="Authentication token required.")

    # ── Get user identity from plex.tv ───────────────────────────
    try:
        plex_user = await get_plex_user(body.authToken)
    except Exception as e:
        logger.error(f"Failed to get Plex user identity: {e}")
        raise HTTPException(status_code=500, detail="Invalid auth token")

    if not plex_user.plex_user_id:
        logger.error(f"Plex ID missing from plex.tv response for {plex_user.email}")
        raise HTTPException(status_code=500, detail="Something went wrong. Try again.")

    # ── Check server access ──────────────────────────────────────
    has_access = await check_server_access(
        user=plex_user,
        admin_token=settings.plex_token,
        machine_id=settings.plex_machine_id,
    )

    if not has_access:
        logger.warning(
            f"Access denied for {plex_user.username} (id={plex_user.plex_user_id}) — "
            f"no access to server {settings.plex_machine_id[:12]}..."
        )
        raise HTTPException(status_code=403, detail="Access denied.")

    # ── Issue JWT ────────────────────────────────────────────────
    token = create_token(
        plex_user_id=plex_user.plex_user_id,
        username=plex_user.username,
        email=plex_user.email,
        thumb=plex_user.thumb,
        plex_token=plex_user.plex_token,
        is_admin=plex_user.is_server_owner,
    )

    logger.info(f"Login successful: {plex_user.username} (admin={plex_user.is_server_owner})")

    return {
        "token": token,
        "user": {
            "plex_user_id": plex_user.plex_user_id,
            "username": plex_user.username,
            "email": plex_user.email,
            "thumb": plex_user.thumb,
            "is_admin": plex_user.is_server_owner,
        },
    }


@router.get("/me")
async def me(user: TokenPayload = Depends(get_current_user)):
    """Return the current authenticated user from JWT."""
    return {
        "plex_user_id": user.plex_user_id,
        "username": user.username,
        "email": user.email,
        "thumb": user.thumb,
        "is_admin": user.is_admin,
    }
