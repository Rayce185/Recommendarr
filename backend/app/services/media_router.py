"""Media routing engine — replaces Redirecterr.

Routes media requests to the correct Radarr/Sonarr instance + root folder
based on configurable filter rules. Rules evaluated top-to-bottom; first match wins.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RoutingTarget:
    instance_name: str
    root_folder: str
    quality_profile_id: int
    tags: list[int] = field(default_factory=list)
    series_type: str = "standard"


@dataclass
class RoutingRule:
    name: str
    media_type: str
    target: str
    root_folder: str
    quality_profile_id: int = 1
    tags: list[int] = field(default_factory=list)
    series_type: str = "standard"
    genre_include: list[str] = field(default_factory=list)
    genre_require: list[str] = field(default_factory=list)
    keyword_include: list[str] = field(default_factory=list)
    company_include: list[str] = field(default_factory=list)
    language_include: list[str] = field(default_factory=list)
    is_catchall: bool = False

    def matches(self, media_type: str, genres: list[str], keywords: list[str],
                companies: list[str], language: str | None = None) -> bool:
        if self.media_type != media_type:
            return False
        if self.is_catchall:
            return True

        genres_lower = {g.lower() for g in genres}
        keywords_lower = {k.lower() for k in keywords}
        companies_lower = {c.lower() for c in companies}

        checks = 0
        passed = 0

        if self.genre_require:
            checks += 1
            if all(g.lower() in genres_lower for g in self.genre_require):
                passed += 1
        if self.genre_include:
            checks += 1
            if any(g.lower() in genres_lower for g in self.genre_include):
                passed += 1
        if self.keyword_include:
            checks += 1
            if any(k.lower() in keywords_lower for k in self.keyword_include):
                passed += 1
        if self.company_include:
            checks += 1
            if any(c.lower() in companies_lower for c in self.company_include):
                passed += 1
        if self.language_include:
            checks += 1
            if language and language.lower() in {l.lower() for l in self.language_include}:
                passed += 1

        return checks > 0 and checks == passed


class MediaRouter:
    def __init__(self, rules: list[RoutingRule] | None = None):
        self.rules: list[RoutingRule] = rules or []

    def route(self, media_type: str, genres: list[str], keywords: list[str],
              companies: list[str] | None = None, language: str | None = None) -> RoutingTarget | None:
        for rule in self.rules:
            if rule.matches(media_type, genres, keywords, companies or [], language):
                logger.info(f"Routing matched rule '{rule.name}' -> {rule.target}:{rule.root_folder}")
                return RoutingTarget(
                    instance_name=rule.target, root_folder=rule.root_folder,
                    quality_profile_id=rule.quality_profile_id,
                    tags=rule.tags, series_type=rule.series_type)
        logger.warning(f"No routing rule matched for {media_type} genres={genres}")
        return None

    @classmethod
    def from_config(cls, config: list[dict]) -> "MediaRouter":
        rules = []
        for c in config:
            rules.append(RoutingRule(
                name=c.get("name", "Unnamed"), media_type=c.get("media_type", "movie"),
                target=c.get("target", ""), root_folder=c.get("root_folder", ""),
                quality_profile_id=c.get("quality_profile_id", 1),
                tags=c.get("tags", []), series_type=c.get("series_type", "standard"),
                genre_include=c.get("genre_include", []), genre_require=c.get("genre_require", []),
                keyword_include=c.get("keyword_include", []), company_include=c.get("company_include", []),
                language_include=c.get("language_include", []), is_catchall=c.get("is_catchall", False)))
        return cls(rules)

    def to_config(self) -> list[dict]:
        result = []
        for r in self.rules:
            d = {"name": r.name, "media_type": r.media_type, "target": r.target,
                 "root_folder": r.root_folder, "quality_profile_id": r.quality_profile_id,
                 "tags": r.tags, "series_type": r.series_type, "is_catchall": r.is_catchall}
            if r.genre_include: d["genre_include"] = r.genre_include
            if r.genre_require: d["genre_require"] = r.genre_require
            if r.keyword_include: d["keyword_include"] = r.keyword_include
            if r.company_include: d["company_include"] = r.company_include
            if r.language_include: d["language_include"] = r.language_include
            result.append(d)
        return result


DEFAULT_ROUTING_RULES: list[dict] = [
    {"name": "Ghibli Movies", "media_type": "movie", "target": "radarr",
     "root_folder": "/media/Movies", "quality_profile_id": 1, "tags": [1],
     "company_include": ["Studio Ghibli"]},
    {"name": "Ghibli Movies (keyword)", "media_type": "movie", "target": "radarr",
     "root_folder": "/media/Movies", "quality_profile_id": 1, "tags": [1],
     "keyword_include": ["studio ghibli", "hayao miyazaki", "ghibli"]},
    {"name": "Kids Movies (Animation+Family)", "media_type": "movie", "target": "radarr",
     "root_folder": "/media/Kinderfilme", "quality_profile_id": 1, "tags": [9],
     "genre_require": ["Animation", "Family"]},
    {"name": "Kids Movies (Family)", "media_type": "movie", "target": "radarr",
     "root_folder": "/media/Kinderfilme", "quality_profile_id": 1, "tags": [9],
     "genre_include": ["Family"]},
    {"name": "All Other Movies", "media_type": "movie", "target": "radarr",
     "root_folder": "/media/Movies", "quality_profile_id": 1, "tags": [1], "is_catchall": True},
    {"name": "Hentai", "media_type": "tv", "target": "sonarr_anime",
     "root_folder": "/media/Hentai", "quality_profile_id": 1, "tags": [12], "series_type": "anime",
     "keyword_include": ["hentai", "erotic", "softcore", "adult animation", "nudity", "sexual content"]},
    {"name": "Ecchi Anime", "media_type": "tv", "target": "sonarr_anime",
     "root_folder": "/media/Ecchi", "quality_profile_id": 1, "tags": [14], "series_type": "anime",
     "keyword_include": ["ecchi", "fanservice", "fan service"]},
    {"name": "Kids Shows (Kids genre)", "media_type": "tv", "target": "sonarr_tv",
     "root_folder": "/media/Kinderserien", "quality_profile_id": 1, "tags": [17],
     "genre_include": ["Kids"]},
    {"name": "Kids Shows (Animation+Family)", "media_type": "tv", "target": "sonarr_tv",
     "root_folder": "/media/Kinderserien", "quality_profile_id": 1, "tags": [17],
     "genre_require": ["Animation", "Family"]},
    {"name": "Kids Shows (keywords)", "media_type": "tv", "target": "sonarr_tv",
     "root_folder": "/media/Kinderserien", "quality_profile_id": 1, "tags": [17],
     "keyword_include": ["kodomomuke", "children's anime", "kids anime", "children", "educational", "preschool"]},
    {"name": "Anime", "media_type": "tv", "target": "sonarr_anime",
     "root_folder": "/media/Anime", "quality_profile_id": 1, "tags": [1], "series_type": "anime",
     "keyword_include": ["anime", "based on manga", "shounen", "seinen", "based on light novel"]},
    {"name": "All Other TV", "media_type": "tv", "target": "sonarr_tv",
     "root_folder": "/media/Series", "quality_profile_id": 1, "tags": [8], "is_catchall": True},
]
