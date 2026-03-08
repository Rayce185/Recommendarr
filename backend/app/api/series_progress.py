"""Series Progress API — TV series completion % per user.

GET /users/{username}/series-progress  — completion data for user's TV shows
"""

import logging
from fastapi import APIRouter, Query, Depends

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.series_progress import get_series_progress

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users/{username}/series-progress")
async def series_progress(
    username: str,
    tmdb_ids: str = Query(None, description="Comma-separated TMDB IDs to filter"),
    current_user: TokenPayload = Depends(get_current_user),
):
    """Get TV series completion percentages for a user.

    Returns watched/total episodes and completion % for each series.
    If tmdb_ids provided, only returns data for those series.
    """
    # Users can only view their own progress (admins see all)
    if current_user.username != username and not current_user.is_admin:
        return {"error": "forbidden", "items": {}}

    id_list = None
    if tmdb_ids:
        try:
            id_list = [int(x.strip()) for x in tmdb_ids.split(",") if x.strip()]
        except ValueError:
            return {"error": "invalid tmdb_ids", "items": {}}

    progress = await get_series_progress(username, id_list)
    return {"items": progress, "total": len(progress)}
