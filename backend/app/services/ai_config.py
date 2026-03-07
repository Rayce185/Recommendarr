"""AI configuration — SQLite-backed, replaces ai_config.json."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy import select

from app.database import get_db, DATA_DIR
from app.models import AiSetting

logger = logging.getLogger(__name__)

# Fallback JSON path (pre-migration or import-time)
AI_CONFIG_JSON = DATA_DIR / "ai_config.json"


@dataclass
class LLMConfig:
    provider: str = ""       # ollama | openai_compat | openai | anthropic
    endpoint: str = ""       # base URL
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 500


@dataclass
class EmbeddingConfig:
    provider: str = "disabled"
    endpoint: str = ""
    api_key: str = ""
    model: str = ""
    chromadb_url: str = ""
    collection_name: str = "recommendarr"


@dataclass
class FeatureFlags:
    ai_mood: bool = True
    ai_explanations: bool = True


@dataclass
class AIConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    features: FeatureFlags = field(default_factory=FeatureFlags)

    @property
    def is_llm_enabled(self) -> bool:
        return bool(self.llm.provider and self.llm.model)

    @property
    def is_embedding_enabled(self) -> bool:
        return self.embedding.provider != "disabled" and bool(self.embedding.model)


def _db_get(key: str, default=None):
    """Get an AI setting from SQLite."""
    try:
        with get_db() as db:
            row = db.execute(
                select(AiSetting).where(AiSetting.key == key)
            ).scalar_one_or_none()
            if row:
                return json.loads(row.value)
    except Exception:
        pass
    return default


def _json_fallback() -> dict:
    """Load from JSON file if DB not ready."""
    if AI_CONFIG_JSON.exists():
        try:
            data = json.loads(AI_CONFIG_JSON.read_text())
            flat = {}
            for section, values in data.items():
                if isinstance(values, dict):
                    for k, v in values.items():
                        flat[f"{section}_{k}"] = v
                else:
                    flat[section] = values
            return flat
        except Exception:
            pass
    return {}


def get_ai_config() -> AIConfig:
    """Build AIConfig from SQLite (or JSON fallback)."""
    cfg = AIConfig()

    # Try DB first
    provider = _db_get("llm_provider")
    if provider is not None:
        cfg.llm.provider = provider or ""
        cfg.llm.endpoint = _db_get("llm_endpoint", "")
        cfg.llm.api_key = _db_get("llm_api_key", "")
        cfg.llm.model = _db_get("llm_model", "")
        cfg.llm.temperature = float(_db_get("llm_temperature", 0.7))
        cfg.llm.max_tokens = int(_db_get("llm_max_tokens", 500))

        cfg.embedding.provider = _db_get("embedding_provider", "disabled")
        cfg.embedding.endpoint = _db_get("embedding_endpoint", "")
        cfg.embedding.api_key = _db_get("embedding_api_key", "")
        cfg.embedding.model = _db_get("embedding_model", "")
        cfg.embedding.chromadb_url = _db_get("embedding_chromadb_url", "")
        cfg.embedding.collection_name = _db_get("embedding_collection_name", "recommendarr")

        cfg.features.ai_mood = _db_get("features_ai_mood", True)
        cfg.features.ai_explanations = _db_get("features_ai_explanations", True)
    else:
        # JSON fallback
        flat = _json_fallback()
        if flat:
            cfg.llm.provider = flat.get("llm_provider", "")
            cfg.llm.endpoint = flat.get("llm_endpoint", "")
            cfg.llm.api_key = flat.get("llm_api_key", "")
            cfg.llm.model = flat.get("llm_model", "")
            cfg.llm.temperature = float(flat.get("llm_temperature", 0.7))
            cfg.llm.max_tokens = int(flat.get("llm_max_tokens", 500))
            cfg.features.ai_mood = flat.get("features_ai_mood", True)
            cfg.features.ai_explanations = flat.get("features_ai_explanations", True)

    # Env var fallback (fresh container, no DB/JSON yet)
    if not cfg.is_llm_enabled:
        env_provider = os.environ.get("AI_LLM_PROVIDER", "")
        if env_provider:
            cfg.llm.provider = env_provider
            cfg.llm.endpoint = os.environ.get("AI_LLM_ENDPOINT", "")
            cfg.llm.api_key = os.environ.get("AI_LLM_API_KEY", "")
            cfg.llm.model = os.environ.get("AI_LLM_MODEL", "")
            cfg.llm.temperature = float(os.environ.get("AI_LLM_TEMPERATURE", "0.7"))
            cfg.llm.max_tokens = int(os.environ.get("AI_LLM_MAX_TOKENS", "500"))
            cfg.features.ai_mood = os.environ.get("AI_FEATURES_MOOD", "true").lower() == "true"
            cfg.features.ai_explanations = os.environ.get("AI_FEATURES_EXPLANATIONS", "true").lower() == "true"
            logger.info(f"AI config from env vars: {env_provider}/{cfg.llm.model}")
            # Persist to DB so UI reflects the env-bootstrapped config
            save_ai_config(cfg)

    return cfg


def save_ai_config(cfg: AIConfig):
    """Persist AIConfig to SQLite."""
    pairs = {
        "llm_provider": cfg.llm.provider,
        "llm_endpoint": cfg.llm.endpoint,
        "llm_api_key": cfg.llm.api_key,
        "llm_model": cfg.llm.model,
        "llm_temperature": cfg.llm.temperature,
        "llm_max_tokens": cfg.llm.max_tokens,
        "embedding_provider": cfg.embedding.provider,
        "embedding_endpoint": cfg.embedding.endpoint,
        "embedding_api_key": cfg.embedding.api_key,
        "embedding_model": cfg.embedding.model,
        "embedding_chromadb_url": cfg.embedding.chromadb_url,
        "embedding_collection_name": cfg.embedding.collection_name,
        "features_ai_mood": cfg.features.ai_mood,
        "features_ai_explanations": cfg.features.ai_explanations,
    }
    try:
        with get_db() as db:
            for key, value in pairs.items():
                row = db.execute(
                    select(AiSetting).where(AiSetting.key == key)
                ).scalar_one_or_none()
                if row:
                    row.value = json.dumps(value)
                else:
                    db.add(AiSetting(key=key, value=json.dumps(value)))
            db.commit()
    except Exception as e:
        logger.error(f"Failed to save AI config: {e}")


# ── Compatibility layer for ai_settings API ──────────────────────

LLM_PROVIDERS = ["disabled", "ollama", "openai_compatible", "openai", "anthropic"]
EMBEDDING_PROVIDERS = ["disabled", "ollama", "openai_compatible"]
AI_FEATURES = ["ai_mood", "ai_explanations"]


class AIConfigStore:
    """Wrapper that provides the old ai_config_store interface over SQLite."""

    def get_display(self, mask_keys: bool = True) -> dict:
        cfg = get_ai_config()
        result = {
            "llm": {
                "provider": cfg.llm.provider,
                "endpoint": cfg.llm.endpoint,
                "api_key": cfg.llm.api_key if not mask_keys else ("***" if cfg.llm.api_key else ""),
                "model": cfg.llm.model,
                "temperature": cfg.llm.temperature,
                "max_tokens": cfg.llm.max_tokens,
            },
            "embedding": {
                "provider": cfg.embedding.provider,
                "endpoint": cfg.embedding.endpoint,
                "api_key": cfg.embedding.api_key if not mask_keys else ("***" if cfg.embedding.api_key else ""),
                "model": cfg.embedding.model,
                "chromadb_url": cfg.embedding.chromadb_url,
                "collection_name": cfg.embedding.collection_name,
            },
            "features": {
                "ai_mood": cfg.features.ai_mood,
                "ai_explanations": cfg.features.ai_explanations,
            },
        }
        return result

    def update(self, data: dict) -> AIConfig:
        cfg = get_ai_config()
        if "llm" in data:
            for k, v in data["llm"].items():
                if v == "***":
                    continue  # Don't overwrite masked keys
                if hasattr(cfg.llm, k):
                    setattr(cfg.llm, k, v)
        if "embedding" in data:
            for k, v in data["embedding"].items():
                if v == "***":
                    continue
                if hasattr(cfg.embedding, k):
                    setattr(cfg.embedding, k, v)
        if "features" in data:
            for k, v in data["features"].items():
                if hasattr(cfg.features, k):
                    setattr(cfg.features, k, v)
        save_ai_config(cfg)
        return cfg

    def reset(self):
        save_ai_config(AIConfig())


_ai_store: Optional[AIConfigStore] = None


def get_ai_config_store() -> AIConfigStore:
    global _ai_store
    if _ai_store is None:
        _ai_store = AIConfigStore()
    return _ai_store
