"""Servarr API clients — backward-compatible re-export module.

Actual implementations live in radarr.py and sonarr.py.
Data models in servarr_models.py.
"""

from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient
from app.clients.servarr_models import ServarrMovie, ServarrSeries

__all__ = ["RadarrClient", "SonarrClient", "ServarrMovie", "ServarrSeries"]
