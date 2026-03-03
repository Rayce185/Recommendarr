"""Application configuration — loads from .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Plex
    plex_url: str = ""
    plex_token: str = ""
    plex_machine_id: str = ""

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
    recommendarr_port: int = 30800

    class Config:
        env_file = [".env", "../.env"]
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
