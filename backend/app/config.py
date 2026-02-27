"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """All configuration loaded from environment / .env file."""

    # ── Application ──────────────────────────────────────────────
    app_name: str = "Recommendarr"
    app_url: str = "http://localhost:30800"
    secret_key: str = "change-me-to-a-random-string"
    debug: bool = False
    log_level: str = "info"

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://recommendarr:recommendarr@recommendarr-db:5432/recommendarr"

    # ── Plex ─────────────────────────────────────────────────────
    plex_url: str = "http://localhost:32400"
    plex_token: Optional[str] = None
    plex_machine_id: Optional[str] = None

    # ── Tautulli ─────────────────────────────────────────────────
    tautulli_url: Optional[str] = None
    tautulli_api_key: Optional[str] = None
    tautulli_webhook_secret: Optional[str] = None

    # ── TMDB ─────────────────────────────────────────────────────
    tmdb_api_key: Optional[str] = None
    tmdb_language: str = "en-US"
    tmdb_cache_ttl_days: int = 7

    # ── Radarr ───────────────────────────────────────────────────
    radarr_url: Optional[str] = None
    radarr_api_key: Optional[str] = None
    radarr_quality_profile_id: Optional[int] = None
    radarr_root_folder: Optional[str] = None

    # ── Sonarr ───────────────────────────────────────────────────
    sonarr_url: Optional[str] = None
    sonarr_api_key: Optional[str] = None
    sonarr_anime_url: Optional[str] = None
    sonarr_anime_api_key: Optional[str] = None

    # ── Seerr ────────────────────────────────────────────────────
    seerr_url: Optional[str] = None
    seerr_api_key: Optional[str] = None

    # ── ChromaDB ─────────────────────────────────────────────────
    chromadb_url: str = "http://chromadb:8000"
    chromadb_collection: str = "recommendarr"

    # ── LLM / Explanations ───────────────────────────────────────
    explanation_mode: str = "auto"  # auto | template | llm
    llm_provider: str = "ollama"   # ollama | openrouter | groq | gemini | custom
    llm_model: str = "auto"
    llm_base_url: str = "http://ollama:11434"
    llm_api_key: Optional[str] = None

    # ── Embeddings ───────────────────────────────────────────────
    embedding_model: str = "nomic-embed-text"
    embedding_url: str = "http://ollama:11434"

    # ── Plex Native Push ─────────────────────────────────────────
    plex_push_playlists: bool = True
    plex_push_collections: bool = False
    plex_push_schedule: str = "daily"

    # ── Weather / Contextual ─────────────────────────────────────
    weather_api_key: Optional[str] = None
    weather_location: str = "Schaffhausen,CH"

    # ── Server ───────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 2

    @property
    def has_plex(self) -> bool:
        return bool(self.plex_token)

    @property
    def has_tautulli(self) -> bool:
        return bool(self.tautulli_url and self.tautulli_api_key)

    @property
    def has_radarr(self) -> bool:
        return bool(self.radarr_url and self.radarr_api_key)

    @property
    def has_sonarr(self) -> bool:
        return bool(self.sonarr_url and self.sonarr_api_key)

    @property
    def has_seerr(self) -> bool:
        return bool(self.seerr_url and self.seerr_api_key)

    @property
    def has_tmdb(self) -> bool:
        return bool(self.tmdb_api_key)

    @property
    def has_ollama(self) -> bool:
        # Checked dynamically at runtime via /api/tags probe
        return True  # optimistic — actual check in LLM service

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
