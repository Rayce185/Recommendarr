"""Genre normalization — split Anime from Animation globally.

TMDB uses "Animation" for both Japanese anime and western animation.
This module detects anime and reclassifies it as a separate genre
so the entire Recommendarr pipeline treats them distinctly.

Detection signals (any match = anime):
  - original_language is Japanese ("ja", "Japanese")
  - Source is the anime Sonarr instance
  - Keywords contain "anime"
"""

_JA_LANGS = {"ja", "japanese"}


def is_anime(original_language=None, is_anime_source=False, keywords=None):
    """Detect if content is anime based on available signals."""
    if is_anime_source:
        return True
    if original_language and original_language.lower() in _JA_LANGS:
        return True
    if keywords and "anime" in [str(k).lower() for k in keywords]:
        return True
    return False


def normalize_genres(genres, original_language=None, is_anime_source=False, keywords=None):
    """Normalize genre list: split Animation into Anime/Animation.

    If the content is detected as anime and has "Animation" in its genres,
    replace "Animation" with "Anime". Returns a new list.
    """
    if not genres or "Animation" not in genres:
        return list(genres) if genres else []
    if is_anime(original_language, is_anime_source, keywords):
        return ["Anime" if g == "Animation" else g for g in genres]
    return list(genres)
