"""Recommendation endpoints — the core product."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db

router = APIRouter()


@router.get("/users/{user_id}/recommendations")
async def get_recommendations(
    user_id: int,
    mode: str = Query("tonight", regex="^(tonight|grab|rediscover|mood|shuffle)$"),
    mood: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    library: Optional[str] = None,
    genres: Optional[str] = None,
    exclude_genres: Optional[str] = None,
    tags: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    language: Optional[str] = None,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """Get personalized recommendations with filters."""
    # TODO: wire up recommendation engine
    return {
        "recommendations": [],
        "meta": {
            "user_id": user_id,
            "mode": mode,
            "total_candidates": 0,
            "filtered_to": 0,
        },
    }


@router.post("/users/{user_id}/feedback")
async def submit_feedback(
    user_id: int,
    tmdb_id: int,
    feedback: str = Query(regex="^(up|down|dismiss)$"),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback on a recommendation."""
    # TODO: insert into feedback table, trigger profile update
    return {"status": "ok"}
