"""List Import API — extract media titles from URLs or pasted text."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.list_import import (
    fetch_url_text, extract_titles_ai, resolve_titles,
    extract_titles_regex, ExtractedTitle,
)
from app.services.ai_config import get_ai_config
from app.services.factory import get_stack

router = APIRouter(prefix="/import", tags=["List Import"])


class ImportRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class BulkActionRequest(BaseModel):
    tmdb_ids: List[dict]  # [{tmdb_id: int, media_type: str}]


@router.post("/extract")
async def extract_and_resolve(
    body: ImportRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Extract media titles from text or URL, resolve against TMDB.

    Provide either `text` (pasted content) or `url` (fetched and parsed).
    Returns extracted titles with TMDB matches.
    """
    if not body.text and not body.url:
        raise HTTPException(400, "Provide either 'text' or 'url'")

    # Step 1: Get source text
    source_text = body.text or ""
    if body.url:
        try:
            source_text = await fetch_url_text(body.url)
        except Exception as e:
            raise HTTPException(400, f"Could not fetch URL: {str(e)[:200]}")

    if len(source_text.strip()) < 10:
        raise HTTPException(400, "Not enough text content to extract from")

    # Step 2: Extract titles
    cfg = get_ai_config()
    ai_used = cfg.is_llm_enabled
    titles = await extract_titles_ai(source_text)

    if not titles:
        return {
            "titles": [],
            "ai_used": ai_used,
            "source_length": len(source_text),
            "message": "No media titles found in the provided content.",
        }

    # Step 3: Resolve against TMDB
    stack = get_stack()
    resolved = await resolve_titles(titles, stack.seerr)

    # Format response
    results = []
    for r in resolved:
        results.append({
            "extracted_title": r.extracted.title,
            "extracted_year": r.extracted.year,
            "extracted_type": r.extracted.media_type,
            "confidence": r.extracted.confidence,
            "matched": r.matched,
            "tmdb_id": r.tmdb_id,
            "tmdb_title": r.tmdb_title,
            "tmdb_type": r.tmdb_type,
            "tmdb_year": r.tmdb_year,
            "poster_url": r.poster_url,
            "vote_average": r.vote_average,
            "overview": r.overview,
        })

    return {
        "titles": results,
        "ai_used": ai_used,
        "source_length": len(source_text),
        "count": len(results),
        "matched_count": sum(1 for r in results if r["matched"]),
    }


@router.post("/bulk-request")
async def bulk_request(
    body: BulkActionRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Bulk-request titles via Seerr (add to library)."""
    stack = get_stack()
    results = []

    for item in body.tmdb_ids[:50]:
        tmdb_id = item.get("tmdb_id")
        media_type = item.get("media_type", "movie")
        if not tmdb_id:
            continue
        try:
            if media_type == "tv":
                resp = await stack.seerr.request_tv(int(tmdb_id))
            else:
                resp = await stack.seerr.request_movie(int(tmdb_id))
            results.append({"tmdb_id": tmdb_id, "status": "ok"})
        except Exception as e:
            results.append({"tmdb_id": tmdb_id, "status": "error", "detail": str(e)[:200]})

    return {
        "processed": len(results),
        "success": sum(1 for r in results if r["status"] == "ok"),
        "results": results,
    }


@router.post("/bulk-watchlist")
async def bulk_watchlist(
    body: BulkActionRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """Bulk-add titles to Plex watchlist."""
    stack = get_stack()
    results = []

    for item in body.tmdb_ids[:50]:
        tmdb_id = item.get("tmdb_id")
        media_type = item.get("media_type", "movie")
        if not tmdb_id:
            continue
        try:
            plex_guid = await stack.plex.resolve_plex_guid(int(tmdb_id), media_type)
            if not plex_guid:
                results.append({"tmdb_id": tmdb_id, "status": "error", "detail": "Could not resolve Plex GUID"})
                continue
            ok = await stack.plex.add_to_watchlist(plex_guid, token_override=user.plex_token)
            results.append({"tmdb_id": tmdb_id, "status": "ok" if ok else "error"})
        except Exception as e:
            results.append({"tmdb_id": tmdb_id, "status": "error", "detail": str(e)[:100]})

    return {
        "processed": len(results),
        "success": sum(1 for r in results if r["status"] == "ok"),
        "results": results,
    }
