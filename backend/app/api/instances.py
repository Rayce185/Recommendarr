"""Instance management API — CRUD for Radarr/Sonarr instances.

Allows adding, removing, updating, and testing *arr instances
without container restarts. All changes persist to settings_store.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth.jwt_handler import TokenPayload, get_current_user
from app.services.factory import get_stack
from app.services.instance_registry import (
    InstanceConfig, save_instance_configs,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["instances"])


def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


class InstanceInput(BaseModel):
    name: str
    type: str          # "radarr" | "sonarr"
    url: str
    api_key: str
    is_default_for: Optional[str] = None  # "movie" | "tv" | None


# ── List all instances ───────────────────────────────────────────

@router.get("/instances")
async def list_instances(user: TokenPayload = Depends(get_current_user)):
    """List all registered Radarr/Sonarr instances with their config and status."""
    stack = get_stack()
    instances = []
    for cfg in stack.registry.configs:
        client = stack.registry.get(cfg.name)
        entry = {
            "name": cfg.name,
            "type": cfg.type,
            "url": cfg.url,
            "api_key_set": bool(cfg.api_key),
            "is_default_for": cfg.is_default_for,
            "connected": False,
        }
        # Quick connection test
        if client:
            try:
                entry["connected"] = await client.test_connection()
            except Exception:
                pass
        instances.append(entry)
    return {"instances": instances}


# ── Get instance detail (with profiles, folders, tags) ───────────

@router.get("/instances/{name}")
async def get_instance_detail(name: str, user: TokenPayload = Depends(get_current_user)):
    """Get full detail for an instance: profiles, root folders, tags."""
    stack = get_stack()
    client = stack.registry.get(name)
    cfg = stack.registry.get_config(name)
    if not client or not cfg:
        raise HTTPException(404, f"Instance '{name}' not found")

    try:
        profiles = await client.get_quality_profiles()
        folders = await client.get_root_folders()
        tags = await client.get_tag_map()
        return {
            "name": cfg.name, "type": cfg.type, "url": cfg.url,
            "is_default_for": cfg.is_default_for,
            "connected": True,
            "quality_profiles": profiles,
            "root_folders": folders,
            "tags": [{"id": k, "label": v} for k, v in tags.items()],
        }
    except Exception as e:
        raise HTTPException(502, f"Cannot reach '{name}': {e}")


# ── Add new instance ────────────────────────────────────────────

@router.post("/instances")
async def add_instance(body: InstanceInput, admin: TokenPayload = Depends(require_admin)):
    """Add a new Radarr/Sonarr instance."""
    stack = get_stack()

    if body.type not in ("radarr", "sonarr"):
        raise HTTPException(400, "type must be 'radarr' or 'sonarr'")

    if stack.registry.get(body.name):
        raise HTTPException(409, f"Instance '{body.name}' already exists")

    cfg = InstanceConfig(
        name=body.name, type=body.type,
        url=body.url, api_key=body.api_key,
        is_default_for=body.is_default_for,
    )

    # If this is set as default, clear previous default for same domain
    if cfg.is_default_for:
        for existing in stack.registry.configs:
            if existing.is_default_for == cfg.is_default_for:
                existing.is_default_for = None

    stack.registry.rebuild_instance(body.name, cfg)
    save_instance_configs(stack.registry.configs)

    # Test connection
    client = stack.registry.get(body.name)
    connected = False
    if client:
        try:
            connected = await client.test_connection()
        except Exception:
            pass

    return {
        "message": f"Added {body.type} instance '{body.name}'",
        "name": body.name, "connected": connected,
    }


# ── Update existing instance ────────────────────────────────────

@router.put("/instances/{name}")
async def update_instance(name: str, body: InstanceInput,
                          admin: TokenPayload = Depends(require_admin)):
    """Update an existing instance. Hot-swaps the client without restart."""
    stack = get_stack()

    if not stack.registry.get(name):
        raise HTTPException(404, f"Instance '{name}' not found")

    cfg = InstanceConfig(
        name=body.name, type=body.type,
        url=body.url, api_key=body.api_key,
        is_default_for=body.is_default_for,
    )

    # Clear previous default if this one claims it
    if cfg.is_default_for:
        for existing in stack.registry.configs:
            if existing.is_default_for == cfg.is_default_for and existing.name != name:
                existing.is_default_for = None

    # Remove old if name changed
    if name != body.name:
        stack.registry.remove_instance(name)

    stack.registry.rebuild_instance(body.name, cfg)
    save_instance_configs(stack.registry.configs)

    return {"message": f"Updated instance '{body.name}'"}


# ── Delete instance ──────────────────────────────────────────────

@router.delete("/instances/{name}")
async def delete_instance(name: str, admin: TokenPayload = Depends(require_admin)):
    """Remove an instance from the registry."""
    stack = get_stack()
    if not stack.registry.remove_instance(name):
        raise HTTPException(404, f"Instance '{name}' not found")

    save_instance_configs(stack.registry.configs)
    return {"message": f"Removed instance '{name}'"}


# ── Test connection ──────────────────────────────────────────────

@router.post("/instances/{name}/test")
async def test_instance(name: str, user: TokenPayload = Depends(get_current_user)):
    """Test connectivity to a specific instance."""
    stack = get_stack()
    client = stack.registry.get(name)
    if not client:
        raise HTTPException(404, f"Instance '{name}' not found")

    try:
        ok = await client.test_connection()
        return {
            "name": name, "connected": ok,
            "message": "Connected" if ok else "Connection failed",
        }
    except Exception as e:
        return {"name": name, "connected": False, "message": str(e)}
