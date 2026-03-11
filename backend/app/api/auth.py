"""Auth API — Plex OAuth login, aligned with Overseerr's flow.

Frontend handles PIN creation and polling directly with plex.tv.
Backend receives the authToken and validates it.

Endpoints:
  POST /auth/plex   — Receive authToken from frontend, validate, return JWT
  GET  /auth/me     — Return current user from JWT (session hydration)
"""

import logging

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from pydantic import BaseModel

from app.auth.plex_oauth import get_plex_user, check_server_access
from app.auth.jwt_handler import create_token, TokenPayload, get_current_user
from app.config import settings
from app.middleware.rate_limit import limiter, AUTH_RATE

logger = logging.getLogger(__name__)



async def _warm_user_caches(username: str):
    """Background task: pre-generate expensive caches on login."""
    import asyncio
    try:
        from app.services.factory import get_stack
        from app.services.cache import get_cache
        from app.services.wrapped import build_wrapped

        stack = get_stack()
        cache = get_cache()

        # Resolve user_id
        users = await stack.tautulli.get_users()
        user_id = None
        for u in users:
            if (u.get("username", "") or u.get("friendly_name", "")) == username:
                user_id = str(u.get("user_id", ""))
                break
        if not user_id:
            return

        # Warm wrapped cache
        cache_key = f"wrapped:{username}:current"
        if cache.get_generic(cache_key) is None:
            try:
                result = await build_wrapped(stack.tautulli, user_id, username)
                cache.set_generic(cache_key, result, ttl=3600)
                logger.debug(f"Warmed wrapped cache for {username}")
            except Exception as e:
                logger.debug(f"Wrapped warmup failed for {username}: {e}")

        # Warm social overlap cache
        from app.services.social import get_taste_overlaps
        social_key = f"social:overlap:{username}:all"
        if cache.get_generic(social_key) is None:
            try:
                overlaps = await get_taste_overlaps(
                    profiler=stack.profiler,
                    tautulli=stack.tautulli,
                    username=username,
                    domain="all",
                )
                result = {
                    "username": username, "domain": "all",
                    "overlaps": [
                        {"username": o.username, "friendly_name": o.friendly_name,
                         "thumb": o.thumb, "overlap_pct": o.overlap_pct,
                         "shared_genres": o.shared_genres, "unique_to_them": o.unique_to_them}
                        for o in overlaps
                    ],
                    "count": len(overlaps),
                }
                cache.set_generic(social_key, result, ttl=1800)
                logger.debug(f"Warmed social cache for {username}")
            except Exception as e:
                logger.debug(f"Social warmup failed for {username}: {e}")

    except Exception as e:
        logger.debug(f"Cache warmup failed for {username}: {e}")

router = APIRouter(prefix="/auth", tags=["auth"])


class PlexAuthRequest(BaseModel):
    authToken: str


@router.post("/plex")
@limiter.limit(AUTH_RATE)
async def auth_plex(request: Request, body: PlexAuthRequest, bg: BackgroundTasks):
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

    bg.add_task(_warm_user_caches, plex_user.username)

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
async def me(user: TokenPayload = Depends(get_current_user), bg: BackgroundTasks = BackgroundTasks()):
    """Return the current authenticated user from JWT."""
    # Warm caches on session restore (fire-and-forget, only if not cached yet)
    bg.add_task(_warm_user_caches, user.username)
    return {
        "plex_user_id": user.plex_user_id,
        "username": user.username,
        "email": user.email,
        "thumb": user.thumb,
        "is_admin": user.is_admin,
    }
