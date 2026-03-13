"""Routing heuristic constants and helpers.

Keyword maps for deterministic route detection from tag/folder names.
Used by routing_autodetect.py as LLM-free fallback.
"""

from typing import Optional

# ── Keyword maps ─────────────────────────────────────────────────

ANIME_KEYWORDS = {"anime", "shounen", "shonen", "seinen", "isekai", "mecha"}
ECCHI_KEYWORDS = {"ecchi", "fanservice", "fan service", "fan-service"}
HENTAI_KEYWORDS = {"hentai", "adult", "adult animation"}
KIDS_KEYWORDS = {"kids", "kinder", "children", "family", "kinderfilme",
                 "kinderserien", "family-friendly"}
MOVIES_KEYWORDS = {"movies", "movie", "filme", "film"}
TV_KEYWORDS = {"tv", "series", "serien", "shows"}

# TMDB metadata triggers for routing rules
ANIME_TMDB_KEYWORDS = ["anime", "based on manga", "shounen", "seinen",
                       "based on light novel", "isekai"]
ECCHI_TMDB_KEYWORDS = ["ecchi", "fanservice", "fan service"]
HENTAI_TMDB_KEYWORDS = ["hentai", "erotic", "adult animation",
                        "sexual content", "softcore"]
KIDS_GENRES = ["Family", "Kids"]
KIDS_TMDB_KEYWORDS = ["children", "educational", "preschool",
                      "kodomomuke", "children's anime", "kids anime"]

# Priority ordering — higher number = later in rule list (less specific)
# Hentai/ecchi must come BEFORE generic anime to match first
CATEGORY_PRIORITY = {
    "hentai": 10, "ecchi": 20, "kids": 30, "anime": 40,
}

# Cross-language folder associations for tag→folder matching
# "kids" (English tag) should match "Kinderfilme" (German folder) etc.
FOLDER_ASSOCIATIONS = {
    "kids": {"kinder", "kinderfilme", "kinderserien", "children", "family"},
    "kinder": {"kids", "children", "family", "kinderfilme", "kinderserien"},
    "anime": {"anime", "animation"},
    "ecchi": {"ecchi", "anime-ecchi"},
    "hentai": {"hentai", "anime-hentai", "adult"},
    "family": {"kids", "kinder", "kinderfilme", "kinderserien", "children"},
}


# ── Helper functions ─────────────────────────────────────────────

def matches_any(text: str, keywords: set) -> bool:
    return any(kw in text for kw in keywords)


def match_folder(tag_label: str, folders: list[str]) -> Optional[str]:
    """Find a root folder whose name relates to the tag.

    Uses direct substring matching, then cross-language associations,
    then falls back to first folder.
    """
    tag_lower = tag_label.lower()
    folder_names = [(f, f.rsplit("/", 1)[-1].lower()) for f in folders]

    # Direct match: tag name in folder name or vice versa
    for path, fname in folder_names:
        if tag_lower in fname or fname in tag_lower:
            return path

    # Cross-language association match
    associations = FOLDER_ASSOCIATIONS.get(tag_lower, set())
    if associations:
        for path, fname in folder_names:
            if any(assoc in fname for assoc in associations):
                return path

    # No match — return first folder as fallback
    return folders[0] if folders else None


def has_rule_for(rules: list, folder: str) -> bool:
    return any(r.get("root_folder") == folder for r in rules)


def get_default_tags(tags_by_label: dict, media_type: str) -> list[int]:
    for label, tid in tags_by_label.items():
        if label in ("movies", "movie", "filme") and media_type == "movie":
            return [tid]
        if label in ("tv", "series", "serien") and media_type == "tv":
            return [tid]
    return []


def get_default_folder(root_folders: list[dict], media_type: str) -> Optional[str]:
    for f in root_folders:
        fname = f["path"].rsplit("/", 1)[-1].lower()
        if media_type == "movie" and matches_any(fname, MOVIES_KEYWORDS):
            return f["path"]
        if media_type == "tv" and matches_any(fname, TV_KEYWORDS):
            return f["path"]
    return root_folders[0]["path"] if root_folders else None


def get_category_priority(tag_label: str) -> int:
    """Return ordering priority for a tag. Lower = more specific = earlier."""
    tag = tag_label.lower()
    for category, prio in CATEGORY_PRIORITY.items():
        if category in tag:
            return prio
    return 99


def make_rule(*, name, media_type, target, root_folder, qp, tags=None,
              series_type="standard", genre_include=None, genre_require=None,
              keyword_include=None, company_include=None, language_include=None,
              is_catchall=False, order=0) -> dict:
    rule = {
        "name": name, "media_type": media_type, "target": target,
        "root_folder": root_folder, "quality_profile_id": qp,
        "tags": tags or [], "series_type": series_type,
        "is_catchall": is_catchall, "_order": order,
    }
    if genre_include:
        rule["genre_include"] = list(genre_include)
    if genre_require:
        rule["genre_require"] = list(genre_require)
    if keyword_include:
        rule["keyword_include"] = list(keyword_include)
    if company_include:
        rule["company_include"] = list(company_include)
    if language_include:
        rule["language_include"] = list(language_include)
    return rule
