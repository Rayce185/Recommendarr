"""Recommendation endpoints — the core product."""

from dataclasses import asdict
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.config import settings
from app.services.embedding import EmbeddingService
from app.services.explanations import ExplanationEngine
from app.services.recommender import RecommendationEngine

router = APIRouter()


def _get_services(db: AsyncSession):
    """Build service stack for recommendations."""
    embedding = EmbeddingService(
        ollama_url=settings.llm_base_url,
        chromadb_url=settings.chromadb_url,
        collection_name="recommendarr",
        model=settings.embedding_model,
    )
    explainer = ExplanationEngine(language="en")
    engine = RecommendationEngine(db=db, embedding=embedding, explainer=explainer)
    return engine


@router.get("/users/{user_id}/recommendations")
async def get_recommendations(
    user_id: int,
    mode: str = Query("tonight", pattern="^(tonight|grab|rediscover)$"),
    limit: int = Query(10, ge=1, le=50),
    genres: Optional[str] = None,
    exclude_genres: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get personalized recommendations with filters.

    Modes:
    - tonight: From your library, unwatched
    - grab: Not in library, worth adding via Radarr/Sonarr
    - rediscover: Previously enjoyed, time to rewatch
    """
    engine = _get_services(db)

    filters = {}
    if genres:
        filters["genres"] = genres
    if exclude_genres:
        filters["exclude_genres"] = exclude_genres
    if year_min:
        filters["year_min"] = year_min
    if year_max:
        filters["year_max"] = year_max
    if language:
        filters["language"] = language

    if mode == "tonight":
        recs = await engine.recommend_tonight(user_id, limit=limit, filters=filters or None)
    elif mode == "grab":
        recs = await engine.recommend_grab(user_id, limit=limit, filters=filters or None)
    elif mode == "rediscover":
        recs = await engine.recommend_rediscover(user_id, limit=limit)
    else:
        raise HTTPException(400, f"Unknown mode: {mode}")

    return {
        "recommendations": [
            {
                "tmdb_id": r.tmdb_id,
                "media_type": r.media_type,
                "title": r.title,
                "year": r.year,
                "poster_url": f"https://image.tmdb.org/t/p/w500{r.poster_path}" if r.poster_path else None,
                "backdrop_url": f"https://image.tmdb.org/t/p/w1280{r.backdrop_path}" if r.backdrop_path else None,
                "trailer_url": f"https://www.youtube-nocookie.com/embed/{r.trailer_key}" if r.trailer_key else None,
                "genres": r.genres,
                "overview": r.overview,
                "vote_average": r.vote_average,
                "runtime_minutes": r.runtime_minutes,
                "original_language": r.original_language,
                "score": r.score,
                "explanation": r.explanation,
                "signals": r.signals,
                "in_library": r.in_library,
            }
            for r in recs
        ],
        "meta": {
            "user_id": user_id,
            "mode": mode,
            "count": len(recs),
            "filters_applied": filters or None,
        },
    }


@router.post("/users/{user_id}/feedback")
async def submit_feedback(
    user_id: int,
    tmdb_id: int = Query(...),
    feedback: str = Query(..., pattern="^(up|down|dismiss)$"),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback on a recommendation — improves future suggestions."""
    from app.models.tables import Feedback as FeedbackModel

    fb = FeedbackModel(
        user_id=user_id,
        tmdb_id=tmdb_id,
        feedback=feedback,
    )
    db.add(fb)
    await db.commit()

    return {"status": "ok", "feedback": feedback, "tmdb_id": tmdb_id}
