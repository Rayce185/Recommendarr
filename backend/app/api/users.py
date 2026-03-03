"""User API v2 — Tautulli as source of truth for users and history."""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional

from app.services.factory import get_stack
from app.services.profile_overrides import get_override_store, ProfileOverrides
from app.auth.jwt_handler import TokenPayload, get_current_user

router = APIRouter()


@router.get("/users")
async def list_users():
    """List all Plex/Tautulli users with basic stats."""
    stack = get_stack()
    try:
        users = await stack.tautulli.get_users()
    except Exception as e:
        raise HTTPException(500, f"Tautulli error: {e}")

    result = []
    for u in users:
        if not u.get("username"):
            continue
        result.append({
            "user_id": u.get("user_id"),
            "username": u.get("username", ""),
            "friendly_name": u.get("friendly_name", ""),
            "thumb": u.get("thumb", ""),
            "is_admin": u.get("is_admin", 0) == 1,
            "is_active": u.get("is_active", 0) == 1,
            "last_seen": u.get("last_seen"),
        })

    return {"users": result, "count": len(result)}


@router.get("/users/{username}/profile")
async def get_user_profile(
    username: str,
    domain: str = Query("all", pattern="^(all|movies|tv|anime)$"),
    depth_months: int = Query(24, ge=1, le=60),
):
    """Build and return user taste profile from watch behavior.

    This is computed live from Tautulli data + Seerr metadata enrichment.
    The first call per user may take 10-30s depending on history size
    and keyword enrichment depth. Subsequent calls in the same session
    are cached in memory.
    """
    stack = get_stack()

    try:
        profile = await stack.profiler.build_profile(
            username=username,
            domain=domain,
            depth_months=depth_months,
            enrich_keywords=True,
            max_enrich=100,
        )
    except Exception as e:
        raise HTTPException(500, f"Profile build error: {e}")

    return {
        "username": profile.username,
        "domain": profile.domain,
        "built_at": profile.built_at.isoformat(),
        "stats": {
            "total_watched": profile.total_watched,
            "total_hours": profile.total_hours,
            "avg_completion": profile.avg_completion,
            "rewatch_count": profile.rewatch_count,
        },
        "genres": [
            {
                "genre": g.genre,
                "score": g.score,
                "watch_count": g.watch_count,
                "avg_completion": g.avg_completion,
                "total_hours": g.total_hours,
            }
            for g in profile.top_genres(15)
        ],
        "keywords": [
            {"keyword": k.keyword, "score": k.score, "count": k.occurrence_count}
            for k in profile.top_keywords(25)
        ],
        "personnel": [
            {"name": p.name, "role": p.role, "score": p.score, "titles": p.title_count}
            for p in profile.top_personnel(15)
        ],
        "avoided_genres": [
            {"genre": g.genre, "score": g.score}
            for g in profile.avoided_genres[:5]
        ],
        "avoided_keywords": [
            {"keyword": k.keyword, "score": k.score}
            for k in profile.avoided_keywords[:10]
        ],
    }


@router.get("/users/{username}/history")
async def get_user_history(
    username: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Recent watch history from Tautulli."""
    stack = get_stack()

    try:
        history = await stack.tautulli.get_history(limit=limit)
    except Exception as e:
        raise HTTPException(500, f"Tautulli error: {e}")

    # Filter to user (Tautulli returns user_id, map to username)
    user_events = []
    for h in history:
        resolved_name = h.user_id
        if stack.user_map:
            resolved_name = stack.user_map.get(str(h.user_id), str(h.user_id))
        if resolved_name == username or str(h.user_id) == username:
            user_events.append({
                "item_key": h.item_key,
                "tmdb_id": h.tmdb_id,
                "media_type": h.media_type,
                "completion_pct": h.completion_pct,
                "duration_seconds": h.duration_seconds,
                "started_at": h.started_at.isoformat() if h.started_at else None,
            })

    return {
        "username": username,
        "history": user_events[:limit],
        "count": len(user_events),
    }


@router.get("/users/{username}/peers")
async def get_taste_peers(
    username: str,
    limit: int = Query(5, ge=1, le=20),
):
    """Find users with similar taste (collaborative filtering peers)."""
    stack = get_stack()

    try:
        peers = await stack.profiler.get_collaborative_peers(username, limit=limit)
    except Exception as e:
        raise HTTPException(500, f"Peer analysis error: {e}")

    return {
        "username": username,
        "peers": [
            {"username": name, "similarity": score}
            for name, score in peers
        ],
    }


@router.get("/users/{username}/profile/overrides")
async def get_profile_overrides(username: str, user: TokenPayload = Depends(get_current_user)):
    """Get the user's manual taste adjustments."""
    store = get_override_store()
    overrides = store.get(username)
    return overrides.to_dict()


@router.put("/users/{username}/profile/overrides")
async def update_profile_overrides(username: str, body: dict, user: TokenPayload = Depends(get_current_user)):
    """Update the user's manual taste adjustments.

    Body: {genre_boosts, genre_blocks, keyword_boosts, keyword_blocks, domains}
    """
    # Authorization: users can only edit their own profile, admins can edit any
    if user.username != username and not user.is_admin:
        raise HTTPException(403, "Cannot modify another user's profile")
    store = get_override_store()
    overrides = ProfileOverrides.from_dict(body)
    store.set(username, overrides)

    # Invalidate cached recs for this user since profile changed
    from app.services.cache import get_cache
    get_cache().invalidate_user(username)

    return {"status": "ok", "overrides": overrides.to_dict()}
