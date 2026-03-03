"""Application configuration — loads from .env file."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = ""

    # Plex
    plex_url: str = "http://192.168.0.111:32400"
    plex_token: str = ""
    plex_machine_id: str = ""

    # Tautulli
    tautulli_url: str = "http://192.168.0.111:30181"
    tautulli_api_key: str = ""

    # TMDB
    tmdb_api_key: str = ""

    # Radarr
    radarr_url: str = "http://192.168.0.111:30878"
    radarr_api_key: str = ""

    # Sonarr
    sonarr_url: str = "http://192.168.0.111:30989"
    sonarr_api_key: str = ""
    sonarr_anime_url: str = "http://192.168.0.111:30990"
    sonarr_anime_api_key: str = ""

    # Seerr
    seerr_url: str = "http://192.168.0.111:30055"
    seerr_api_key: str = ""

    # AI/Embedding
    llm_base_url: str = "http://192.168.0.111:20434"
    chromadb_url: str = "http://192.168.0.111:20002"
    embedding_model: str = "nomic-embed-text"

    # JWT / Auth
    jwt_secret: str = ""
    jwt_expiry_hours: int = 720  # 30 days

    # App
    debug: bool = True
    log_level: str = "DEBUG"
    recommendarr_port: int = 30800

    class Config:
        env_file = [".env", "../.env", "/mnt/user/system/claude/recommendarr/src/.env"]
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
