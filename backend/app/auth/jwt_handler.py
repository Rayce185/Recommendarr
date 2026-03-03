"""JWT session management for Plex OAuth.

Creates and validates JWT tokens containing Plex user identity.
Tokens carry the user's Plex token for per-user watchlist operations.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────

ALGORITHM = "HS256"
ISSUER = "recommendarr"


# ── Token Data ───────────────────────────────────────────────────

@dataclass
class TokenPayload:
    """Decoded JWT payload — the authenticated user's identity."""
    plex_user_id: int
    username: str
    email: str
    thumb: str
    plex_token: str
    is_admin: bool
    exp: int
    iat: int


# ── Encode / Decode ──────────────────────────────────────────────

def create_token(
    plex_user_id: int,
    username: str,
    email: str,
    thumb: str,
    plex_token: str,
    is_admin: bool = False,
) -> str:
    """Create a signed JWT with Plex user identity.

    Token contains the user's Plex auth token for per-user
    watchlist operations. Expiry is configurable via JWT_EXPIRY_HOURS.
    """
    now = int(time.time())
    expiry_seconds = settings.jwt_expiry_hours * 3600

    payload = {
        "sub": str(plex_user_id),
        "username": username,
        "email": email,
        "thumb": thumb,
        "plex_token": plex_token,
        "is_admin": is_admin,
        "iss": ISSUER,
        "iat": now,
        "exp": now + expiry_seconds,
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    logger.info(f"JWT created for {username} (expires in {settings.jwt_expiry_hours}h)")
    return token


def decode_token(token: str) -> Optional[TokenPayload]:
    """Decode and validate a JWT. Returns None if invalid/expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
        return TokenPayload(
            plex_user_id=int(payload["sub"]),
            username=payload["username"],
            email=payload.get("email", ""),
            thumb=payload.get("thumb", ""),
            plex_token=payload["plex_token"],
            is_admin=payload.get("is_admin", False),
            exp=payload["exp"],
            iat=payload["iat"],
        )
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT invalid: {e}")
        return None


# ── FastAPI Dependency ───────────────────────────────────────────

from fastapi import Request, HTTPException


async def get_current_user(request: Request) -> TokenPayload:
    """FastAPI dependency — extract and validate JWT from Authorization header.

    Usage in route:
        @router.get("/protected")
        async def protected(user: TokenPayload = Depends(get_current_user)):
            ...
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]  # Strip "Bearer "
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


async def get_optional_user(request: Request) -> Optional[TokenPayload]:
    """FastAPI dependency — extract JWT if present, return None if not.

    Use for endpoints that work both authenticated and unauthenticated,
    with degraded functionality for anonymous users.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    return decode_token(token)
