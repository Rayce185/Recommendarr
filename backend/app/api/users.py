"""User profile and history endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    """List all Plex users with profile status."""
    # TODO: query users table, return with profile freshness
    return {"users": []}


@router.get("/users/{user_id}/profile")
async def get_user_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    """User taste profile summary."""
    # TODO: return taste vector, genre weights, top influences
    return {"user_id": user_id, "profile": None}


@router.get("/users/{user_id}/history")
async def get_user_history(
    user_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Watch history with signals."""
    # TODO: query watch_history, join tmdb_cache
    return {"user_id": user_id, "history": [], "total": 0}
