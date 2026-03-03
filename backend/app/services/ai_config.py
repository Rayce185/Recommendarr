"""AI Integration configuration and provider abstraction.

Two independent subsystems:
1. LLM (text generation) — mood parsing, explanations, future chat
2. Embeddings (vector search) — semantic search, vibe matching (future)

Provider types:
- ollama: Local Ollama instance (no API key needed)
- openai_compatible: LiteLLM, vLLM, LocalAI, or any OpenAI-API-compatible endpoint
- openai: OpenAI direct
- anthropic: Anthropic direct (LLM only, no embeddings)

Settings persist in /app/data/ai_config.json.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

AI_CONFIG_FILE = Path("/app/data/ai_config.json")

# Valid provider types
LLM_PROVIDERS = ["disabled", "ollama", "openai_compatible", "openai", "anthropic"]
EMBEDDING_PROVIDERS = ["disabled", "ollama", "openai_compatible"]

# Feature flags
AI_FEATURES = ["ai_mood", "ai_explanations"]


@dataclass
class LLMConfig:
    """LLM (text generation) provider configuration."""
    provider: str = "disabled"       # disabled | ollama | openai_compatible | openai | anthropic
    endpoint: str = ""               # Base URL (not needed for openai/anthropic with defaults)
    api_key: str = ""                # API key (not needed for ollama)
    model: str = ""                  # Model name/ID
    temperature: float = 0.7
    max_tokens: int = 500


@dataclass
class EmbeddingConfig:
    """Embedding provider configuration (Phase 2+)."""
    provider: str = "disabled"       # disabled | ollama | openai_compatible
    endpoint: str = ""               # Base URL
    api_key: str = ""
    model: str = ""                  # Embedding model name
    chromadb_url: str = ""           # ChromaDB endpoint
    collection_name: str = "recommendarr"


@dataclass
class AIFeatures:
    """Feature toggles — which AI capabilities are active."""
    ai_mood: bool = False            # LLM-enhanced mood parsing
    ai_explanations: bool = False    # LLM-generated explanations


@dataclass
class AIConfig:
    """Complete AI integration configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    features: AIFeatures = field(default_factory=AIFeatures)

    @property
    def is_llm_enabled(self) -> bool:
        return self.llm.provider != "disabled" and bool(self.llm.model)

    @property
    def is_embedding_enabled(self) -> bool:
        return self.embedding.provider != "disabled" and bool(self.embedding.model) and bool(self.embedding.chromadb_url)

    @property
    def any_feature_enabled(self) -> bool:
        return self.features.ai_mood or self.features.ai_explanations

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AIConfig":
        cfg = cls()
        if "llm" in data:
            for k, v in data["llm"].items():
                if hasattr(cfg.llm, k):
                    setattr(cfg.llm, k, v)
        if "embedding" in data:
            for k, v in data["embedding"].items():
                if hasattr(cfg.embedding, k):
                    setattr(cfg.embedding, k, v)
        if "features" in data:
            for k, v in data["features"].items():
                if hasattr(cfg.features, k):
                    setattr(cfg.features, k, bool(v))
        return cfg


class AIConfigStore:
    """Persistent AI config — loads from / saves to JSON file."""

    def __init__(self):
        self._config = AIConfig()
        self._load()

    def _load(self):
        if AI_CONFIG_FILE.exists():
            try:
                with open(AI_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                self._config = AIConfig.from_dict(data)
                logger.info(f"AI config loaded: LLM={self._config.llm.provider}, features={self._config.features}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load AI config: {e}")

    def save(self):
        AI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AI_CONFIG_FILE, "w") as f:
            json.dump(self._config.to_dict(), f, indent=2)

    @property
    def config(self) -> AIConfig:
        return self._config

    def update(self, data: dict) -> AIConfig:
        """Partial update — merge incoming data into current config."""
        self._config = AIConfig.from_dict({
            **self._config.to_dict(),
            **data,
        })
        self.save()
        return self._config

    def get_display(self, mask_keys: bool = True) -> dict:
        """Return config for UI display (with optional key masking)."""
        d = self._config.to_dict()
        if mask_keys:
            if d["llm"]["api_key"]:
                k = d["llm"]["api_key"]
                d["llm"]["api_key"] = f"{k[:4]}...{k[-4:]}" if len(k) >= 12 else "****"
            if d["embedding"]["api_key"]:
                k = d["embedding"]["api_key"]
                d["embedding"]["api_key"] = f"{k[:4]}...{k[-4:]}" if len(k) >= 12 else "****"
        return d

    def reset(self):
        """Reset to defaults (disabled)."""
        self._config = AIConfig()
        self.save()


# Singleton
_store: Optional[AIConfigStore] = None


def get_ai_config_store() -> AIConfigStore:
    global _store
    if _store is None:
        _store = AIConfigStore()
    return _store


def get_ai_config() -> AIConfig:
    """Quick access to current AI config."""
    return get_ai_config_store().config
