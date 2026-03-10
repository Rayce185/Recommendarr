"""AI Integration API — configure and test LLM/embedding providers."""

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.services.ai_config import (
    get_ai_config_store, LLMConfig, EmbeddingConfig,
    LLM_PROVIDERS, EMBEDDING_PROVIDERS, AI_FEATURES,
)
from app.services.ai_client import test_llm_connection, list_models
from app.auth.jwt_handler import TokenPayload, get_current_user
from app.middleware.rate_limit import limiter, AI_RATE


def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


router = APIRouter(prefix="/ai", tags=["AI Integration"])


@router.get("/config")
async def get_ai_config(
    admin: TokenPayload = Depends(require_admin),
    edit: bool = Query(False, description="Return unmasked API keys"),
):
    """Get current AI configuration."""
    store = get_ai_config_store()
    return store.get_display(mask_keys=not edit)


class AIConfigUpdate(BaseModel):
    llm: Optional[Dict[str, Any]] = None
    embedding: Optional[Dict[str, Any]] = None
    features: Optional[Dict[str, bool]] = None


@router.put("/config")
async def update_ai_config(
    body: AIConfigUpdate,
    admin: TokenPayload = Depends(require_admin),
):
    """Update AI configuration. Partial updates supported."""
    store = get_ai_config_store()
    update_data = {}
    if body.llm is not None:
        # Validate provider
        if "provider" in body.llm and body.llm["provider"] not in LLM_PROVIDERS:
            raise HTTPException(400, f"Invalid LLM provider. Must be one of: {LLM_PROVIDERS}")
        update_data["llm"] = body.llm
    if body.embedding is not None:
        if "provider" in body.embedding and body.embedding["provider"] not in EMBEDDING_PROVIDERS:
            raise HTTPException(400, f"Invalid embedding provider. Must be one of: {EMBEDDING_PROVIDERS}")
        update_data["embedding"] = body.embedding
    if body.features is not None:
        for k in body.features:
            if k not in AI_FEATURES:
                raise HTTPException(400, f"Unknown feature flag: {k}. Must be one of: {AI_FEATURES}")
        update_data["features"] = body.features

    cfg = store.update(update_data)
    return {
        "status": "ok",
        "config": store.get_display(mask_keys=True),
        "message": "AI configuration updated.",
    }


@router.post("/config/reset")
async def reset_ai_config(admin: TokenPayload = Depends(require_admin)):
    """Reset AI config to defaults (all disabled)."""
    store = get_ai_config_store()
    store.reset()
    return {"status": "ok", "message": "AI configuration reset to defaults."}


class TestConnectionRequest(BaseModel):
    provider: str
    endpoint: str = ""
    api_key: str = ""
    model: str = ""


@router.post("/test")
@limiter.limit(AI_RATE)
async def test_ai_connection(
    request: Request,
    body: TestConnectionRequest,
    admin: TokenPayload = Depends(require_admin),
):
    """Test LLM provider connectivity without saving config."""
    llm = LLMConfig(
        provider=body.provider,
        endpoint=body.endpoint,
        api_key=body.api_key,
        model=body.model,
    )
    result = await test_llm_connection(llm)
    return result


@router.post("/models")
@limiter.limit(AI_RATE)
async def get_available_models(
    request: Request,
    body: TestConnectionRequest,
    admin: TokenPayload = Depends(require_admin),
):
    """List available models from a provider (for model selector dropdown)."""
    llm = LLMConfig(
        provider=body.provider,
        endpoint=body.endpoint,
        api_key=body.api_key,
        model=body.model or "",
    )
    models = await list_models(llm)
    return {"models": models}


@router.get("/providers")
async def get_provider_info(admin: TokenPayload = Depends(require_admin)):
    """Return available provider types and their configuration requirements."""
    return {
        "llm_providers": [
            {"id": "disabled", "label": "Disabled", "needs_endpoint": False, "needs_key": False},
            {"id": "ollama", "label": "Ollama (Local)", "needs_endpoint": True, "needs_key": False,
             "endpoint_placeholder": "http://192.168.0.111:11434", "endpoint_help": "Ollama API URL"},
            {"id": "openai_compatible", "label": "OpenAI-Compatible (LiteLLM, vLLM, LocalAI)", "needs_endpoint": True, "needs_key": True,
             "endpoint_placeholder": "http://192.168.0.111:4000/v1", "endpoint_help": "Any OpenAI-compatible API endpoint"},
            {"id": "openai", "label": "OpenAI", "needs_endpoint": False, "needs_key": True,
             "endpoint_placeholder": "https://api.openai.com/v1", "endpoint_help": "Uses default OpenAI endpoint"},
            {"id": "anthropic", "label": "Anthropic", "needs_endpoint": False, "needs_key": True,
             "endpoint_placeholder": "", "endpoint_help": "Uses Anthropic Messages API"},
        ],
        "embedding_providers": [
            {"id": "disabled", "label": "Disabled", "needs_endpoint": False, "needs_key": False},
            {"id": "ollama", "label": "Ollama (Local)", "needs_endpoint": True, "needs_key": False,
             "endpoint_placeholder": "http://192.168.0.111:11434"},
            {"id": "openai_compatible", "label": "OpenAI-Compatible", "needs_endpoint": True, "needs_key": True,
             "endpoint_placeholder": "http://host:port/v1"},
        ],
        "features": [
            {"id": "ai_mood", "label": "AI Mood Parsing", "description": "Use LLM to understand natural language mood queries like 'something cozy but not boring'. Falls back to keyword matching when disabled.", "requires": "llm"},
            {"id": "ai_explanations", "label": "AI Explanations", "description": "Generate natural language explanations for why something was recommended, using your watch history context.", "requires": "llm"},
        ],
    }
