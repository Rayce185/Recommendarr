"""Application configuration — loads from .env file, with JSON overlay support."""

from pydantic_settings import BaseSettings
from typing import Any


class Settings(BaseSettings):
    # Plex
    plex_url: str = ""
    plex_token: str = ""
    plex_machine_id: str = ""
    plex_external_url: str = ""  # e.g. https://plex.example.com or auto (uses app.plex.tv)

    # Tautulli
    tautulli_url: str = ""
    tautulli_api_key: str = ""

    # TMDB
    tmdb_api_key: str = ""

    # Radarr
    radarr_url: str = ""
    radarr_api_key: str = ""

    # Sonarr
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    sonarr_anime_url: str = ""
    sonarr_anime_api_key: str = ""

    # Seerr
    seerr_url: str = ""
    seerr_api_key: str = ""

    # AI/Embedding (optional)
    llm_base_url: str = ""
    chromadb_url: str = ""
    embedding_model: str = "nomic-embed-text"

    # JWT / Auth
    jwt_secret: str = ""
    jwt_expiry_hours: int = 720  # 30 days

    # App
    debug: bool = False
    log_level: str = "info"
    recommendarr_port: int = 5055

    class Config:
        env_file = [".env", "../.env"]
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def apply_overrides(self, overrides: dict[str, Any]):
        """Apply runtime overrides from settings store."""
        for key, value in overrides.items():
            if hasattr(self, key):
                # Type coerce based on field type
                field_type = type(getattr(self, key))
                try:
                    if field_type == bool:
                        if isinstance(value, str):
                            value = value.lower() in ("true", "1", "yes")
                    elif field_type == int:
                        value = int(value)
                    object.__setattr__(self, key, value)
                except (ValueError, TypeError):
                    pass  # Skip bad values


settings = Settings()

# Apply any persistent overrides on import
def _apply_stored_overrides():
    try:
        from app.services.settings_store import get_settings_store
        store = get_settings_store()
        overrides = store.get_all_overrides()
        if overrides:
            settings.apply_overrides(overrides)
            print(f"[config] Applied {len(overrides)} setting overrides from store")
    except Exception as e:
        print(f"[config] Could not load settings store: {e}")

_apply_stored_overrides()
