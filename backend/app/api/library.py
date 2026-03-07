"""Library management API — add media to Radarr/Sonarr with intelligent routing."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.factory import get_stack
from app.services.settings_store import get_settings_store
from app.services.media_router import MediaRouter, DEFAULT_ROUTING_RULES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["library"])

def _log_request(username: str, tmdb_id: int, media_type: str, title: str,
                 instance: str, root_folder: str, tags: list, status: str):
    """Log request to SQLite + fire ChromaDB sync."""
    import json as _json
    try:
        from app.database import get_db
        from app.models.tables import RequestLog
        with get_db() as db:
            db.add(RequestLog(
                username=username, tmdb_id=tmdb_id, media_type=media_type,
                title=title, instance=instance, root_folder=root_folder,
                tags=_json.dumps(tags) if tags else None, status=status,
            ))
            db.commit()
    except Exception as e:
        logger.debug(f"Request log failed: {e}")

    from app.services.chroma_sync import get_chroma_sync, fire_and_forget
    sync = get_chroma_sync()
    if sync:
        fire_and_forget(sync.sync_request(username, tmdb_id, media_type, title,
                                          instance, root_folder, status))




class AddMediaRequest(BaseModel):
    tmdb_id: int
    media_type: str
    target_instance: Optional[str] = None
    root_folder: Optional[str] = None
    quality_profile_id: Optional[int] = None
    tags: Optional[list[int]] = None
    series_type: Optional[str] = None
    search_now: bool = True


class AddMediaResponse(BaseModel):
    success: bool
    message: str
    tmdb_id: int
    title: str = ""
    instance: str = ""
    root_folder: str = ""
    already_exists: bool = False


@router.post("/library/add", response_model=AddMediaResponse)
async def add_to_library(req: AddMediaRequest, user: TokenPayload = Depends(get_current_user)):
    """Add a movie or TV show to Radarr/Sonarr using routing rules."""
    stack = get_stack()
    store = get_settings_store()

    try:
        detail = await stack.tmdb.get_detail(req.tmdb_id, req.media_type)
    except Exception as e:
        raise HTTPException(502, f"TMDB lookup failed: {e}")

    title = detail.get("title", f"TMDB {req.tmdb_id}")
    genres = detail.get("genres", [])
    keywords = detail.get("keywords", [])
    companies = detail.get("production_companies", [])
    language = detail.get("original_language")

    if req.target_instance and req.root_folder:
        instance_name = req.target_instance
        root_folder = req.root_folder
        qp_id = req.quality_profile_id or 1
        tags = req.tags or []
        series_type = req.series_type or "standard"
    else:
        rules_config = store.get("routing_rules") or DEFAULT_ROUTING_RULES
        router_engine = MediaRouter.from_config(rules_config)
        target = router_engine.route(req.media_type, genres, keywords, companies, language)
        if not target:
            raise HTTPException(422, f"No routing rule matched for '{title}' (type={req.media_type}, genres={genres})")
        instance_name = target.instance_name
        root_folder = target.root_folder
        qp_id = req.quality_profile_id or target.quality_profile_id
        tags = req.tags if req.tags is not None else target.tags
        series_type = req.series_type or target.series_type

    logger.info(f"Routing '{title}' -> {instance_name}:{root_folder}")

    try:
        if req.media_type == "movie":
            radarr = stack.registry.get(instance_name)
            if not radarr:
                radarr = stack.registry.get_default_for("movie")
            if not radarr:
                raise HTTPException(422, f"No Radarr instance '{instance_name}' configured")
            if await radarr.movie_exists(req.tmdb_id):
                return AddMediaResponse(success=True, message=f"'{title}' already in library",
                    tmdb_id=req.tmdb_id, title=title, instance=instance_name,
                    root_folder=root_folder, already_exists=True)
            result = await radarr.add_movie(tmdb_id=req.tmdb_id, quality_profile_id=qp_id,
                root_folder=root_folder, tags=tags, search_now=req.search_now)
            _log_request(user.username, req.tmdb_id, req.media_type, title, instance_name, root_folder, tags, "added")
            return AddMediaResponse(success=True, message=f"Added '{title}' to {instance_name}",
                tmdb_id=req.tmdb_id, title=result.get("title", title),
                instance=instance_name, root_folder=root_folder)

        elif req.media_type == "tv":
            sonarr = stack.registry.get(instance_name)
            if not sonarr:
                sonarr = stack.registry.get_default_for("tv")
            if not sonarr:
                raise HTTPException(422, f"No Sonarr instance '{instance_name}' configured")
            tvdb_id = detail.get("tvdb_id")
            if tvdb_id and await sonarr.series_exists(tvdb_id=tvdb_id):
                return AddMediaResponse(success=True, message=f"'{title}' already in library",
                    tmdb_id=req.tmdb_id, title=title, instance=instance_name,
                    root_folder=root_folder, already_exists=True)
            if not tvdb_id and await sonarr.series_exists(tmdb_id=req.tmdb_id):
                return AddMediaResponse(success=True, message=f"'{title}' already in library",
                    tmdb_id=req.tmdb_id, title=title, instance=instance_name,
                    root_folder=root_folder, already_exists=True)
            result = await sonarr.add_series(tvdb_id=tvdb_id,
                tmdb_id=req.tmdb_id if not tvdb_id else None,
                quality_profile_id=qp_id, root_folder=root_folder, tags=tags,
                search_now=req.search_now, series_type=series_type)
            _log_request(user.username, req.tmdb_id, req.media_type, title, instance_name, root_folder, tags, "added")
            return AddMediaResponse(success=True, message=f"Added '{title}' to {instance_name}",
                tmdb_id=req.tmdb_id, title=result.get("title", title),
                instance=instance_name, root_folder=root_folder)
        else:
            raise HTTPException(400, f"Unsupported media_type: {req.media_type}")

    except ValueError as e:
        err_msg = str(e).lower()
        if "already" in err_msg or "exists" in err_msg or "configured" in err_msg:
            return AddMediaResponse(success=True, message=f"'{title}' already in library",
                tmdb_id=req.tmdb_id, title=title, instance=instance_name,
                root_folder=root_folder, already_exists=True)
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Failed to add '{title}': {e}")
        raise HTTPException(502, f"Failed to add to {instance_name}: {e}")


@router.post("/library/route-preview")
async def preview_routing(tmdb_id: int = Query(...), media_type: str = Query("movie"),
                           user: TokenPayload = Depends(get_current_user)):
    """Preview routing without adding."""
    stack = get_stack()
    store = get_settings_store()
    try:
        detail = await stack.tmdb.get_detail(tmdb_id, media_type)
    except Exception as e:
        raise HTTPException(502, f"TMDB lookup failed: {e}")

    rules_config = store.get("routing_rules") or DEFAULT_ROUTING_RULES
    router_engine = MediaRouter.from_config(rules_config)
    target = router_engine.route(media_type, detail.get("genres", []),
        detail.get("keywords", []), detail.get("production_companies", []),
        detail.get("original_language"))

    return {
        "title": detail.get("title"), "tmdb_id": tmdb_id, "media_type": media_type,
        "genres": detail.get("genres", []), "keywords": detail.get("keywords", [])[:20],
        "companies": detail.get("production_companies", []),
        "language": detail.get("original_language"),
        "routed_to": {"instance": target.instance_name, "root_folder": target.root_folder,
            "quality_profile_id": target.quality_profile_id, "tags": target.tags,
            "series_type": target.series_type} if target else None,
    }


@router.get("/system/routing")
async def get_routing_rules(user: TokenPayload = Depends(get_current_user)):
    store = get_settings_store()
    rules = store.get("routing_rules")
    return {"rules": rules or DEFAULT_ROUTING_RULES, "is_default": rules is None}


@router.put("/system/routing")
async def update_routing_rules(body: dict, user: TokenPayload = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    rules = body.get("rules")
    if not isinstance(rules, list):
        raise HTTPException(400, "Expected { rules: [...] }")
    try:
        MediaRouter.from_config(rules)
    except Exception as e:
        raise HTTPException(400, f"Invalid rules: {e}")
    store = get_settings_store()
    store.update({"routing_rules": rules})
    return {"message": f"Updated {len(rules)} routing rules", "rules": rules}


@router.post("/system/routing/reset")
async def reset_routing_rules(user: TokenPayload = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    store = get_settings_store()
    store.remove("routing_rules")
    return {"message": "Reset to default routing rules", "rules": DEFAULT_ROUTING_RULES}


@router.get("/system/instances")
async def get_instance_info(user: TokenPayload = Depends(get_current_user)):
    """Get all *arr instances with quality profiles, root folders, tags."""
    stack = get_stack()
    instances = {}
    for cfg in stack.registry.configs:
        name = cfg.name
        client = stack.registry.get(name)
        if not client:
            continue
        try:
            profiles = await client.get_quality_profiles()
            folders = await client.get_root_folders()
            tags = await client.get_tag_map()
            inst_type = cfg.type
            instances[name] = {"type": inst_type, "url": client.url, "connected": True,
                "quality_profiles": profiles, "root_folders": folders,
                "tags": [{"id": k, "label": v} for k, v in tags.items()]}
        except Exception as e:
            instances[name] = {"type": cfg.type,
                "connected": False, "error": str(e)}
    return instances


@router.post("/system/routing/auto-detect")
async def auto_detect_routing(admin: TokenPayload = Depends(get_current_user)):
    """Auto-detect routing rules from instance tags and root folders.

    Analyzes all registered *arr instances, then generates rules using
    AI (if configured) or deterministic heuristics as fallback.
    Returns suggested rules for preview — does NOT auto-apply.
    """
    if not admin.is_admin:
        raise HTTPException(403, "Admin only")
    stack = get_stack()
    from app.services.routing_autodetect import auto_detect_rules
    result = await auto_detect_rules(stack.registry)
    return result
