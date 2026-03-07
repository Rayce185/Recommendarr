"""Auto-detect routing rules from Servarr instance configurations.

Analyzes tags, root folders, and quality profiles across all registered
*arr instances and generates intelligent routing rules. Works in two modes:

1. AI mode: Sends instance data to LLM for intelligent rule generation
2. Heuristic mode: Uses keyword matching on tag/folder names (no LLM needed)

Both modes produce the same routing rule format consumed by MediaRouter.
"""

import json
import logging
import re
from typing import Optional

from app.services.routing_heuristics import (
    ANIME_KEYWORDS, ECCHI_KEYWORDS, HENTAI_KEYWORDS, KIDS_KEYWORDS,
    ANIME_TMDB_KEYWORDS, ECCHI_TMDB_KEYWORDS, HENTAI_TMDB_KEYWORDS,
    KIDS_GENRES, KIDS_TMDB_KEYWORDS,
    matches_any, match_folder, has_rule_for,
    get_default_tags, get_default_folder, make_rule,
    get_category_priority,
)

logger = logging.getLogger(__name__)


async def auto_detect_rules(registry) -> dict:
    """Analyze all registered instances and generate routing rules.

    Returns {
        "rules": [...],
        "method": "ai"|"heuristic",
        "instance_analysis": {...}
    }
    """
    analysis = await _analyze_instances(registry)

    rules = await _ai_generate_rules(analysis)
    if rules:
        return {"rules": rules, "method": "ai", "instance_analysis": analysis}

    rules = _heuristic_generate_rules(analysis)
    return {"rules": rules, "method": "heuristic", "instance_analysis": analysis}


async def _analyze_instances(registry) -> dict:
    """Fetch tags, root folders, quality profiles from all instances."""
    analysis = {}
    for cfg in registry.configs:
        client = registry.get(cfg.name)
        if not client:
            continue
        entry = {
            "name": cfg.name, "type": cfg.type, "url": cfg.url,
            "is_default_for": cfg.is_default_for,
            "tags": [], "root_folders": [], "quality_profiles": [],
        }
        try:
            tags = await client.get_tag_map()
            entry["tags"] = [{"id": k, "label": v} for k, v in tags.items()]
        except Exception as e:
            logger.debug(f"Tags fetch failed for {cfg.name}: {e}")
        try:
            entry["root_folders"] = await client.get_root_folders()
        except Exception as e:
            logger.debug(f"Root folders fetch failed for {cfg.name}: {e}")
        try:
            entry["quality_profiles"] = await client.get_quality_profiles()
        except Exception as e:
            logger.debug(f"Quality profiles fetch failed for {cfg.name}: {e}")
        analysis[cfg.name] = entry
    return analysis


async def _ai_generate_rules(analysis: dict) -> Optional[list[dict]]:
    """Use LLM to generate routing rules from instance analysis."""
    try:
        from app.services.ai_client import llm_complete
    except ImportError:
        return None

    system_prompt = (
        "You are a media server routing expert. Analyze Radarr/Sonarr instance "
        "configs (tags, root folders) and generate routing rules.\n\n"
        "Rules evaluate top-to-bottom, first match wins. End with catchalls.\n\n"
        "Respond with ONLY a JSON array. No markdown, no explanation.\n"
        "Each rule: {name, media_type (movie|tv), target (instance name), "
        "root_folder (exact path), quality_profile_id (int), tags (id array), "
        "series_type (standard|anime), is_catchall (bool), "
        "genre_include? (TMDB genres, any-match), genre_require? (ALL required), "
        "keyword_include? (TMDB keywords, any-match), "
        "company_include?, language_include?}\n\n"
        "Common patterns:\n"
        "- anime tags → keyword_include [\"anime\",\"based on manga\"]\n"
        "- ecchi tags → keyword_include [\"ecchi\",\"fanservice\"]\n"
        "- hentai tags → keyword_include [\"hentai\",\"erotic\"]\n"
        "- kids/kinder → genre_include [\"Family\",\"Kids\"]\n"
        "- Order: hentai → ecchi → anime → kids → catchall"
    )
    user_prompt = (
        f"Analyze these instances and generate routing rules as JSON:\n\n"
        f"{json.dumps(analysis, indent=2)}\n\n"
        f"Use exact instance names, folder paths, tag IDs, and profile IDs."
    )

    try:
        response = await llm_complete(user_prompt, system=system_prompt)
        if not response:
            return None
        cleaned = re.sub(r'^```json?\s*', '', response.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)
        rules = json.loads(cleaned)
        if isinstance(rules, list) and len(rules) > 0:
            logger.info(f"AI generated {len(rules)} routing rules")
            return rules
    except json.JSONDecodeError as e:
        logger.warning(f"AI returned invalid JSON: {e}")
    except Exception as e:
        logger.warning(f"AI routing generation failed: {e}")
    return None


def _heuristic_generate_rules(analysis: dict) -> list[dict]:
    """Generate routing rules using keyword heuristics. No LLM needed."""
    rules = []
    order = 0

    for inst_name, inst in analysis.items():
        tags_by_label = {t["label"].lower(): t["id"] for t in inst["tags"]}
        folders = [f["path"] for f in inst["root_folders"]]
        default_qp = inst["quality_profiles"][0]["id"] if inst["quality_profiles"] else 1
        media_type = "movie" if inst["type"] == "radarr" else "tv"

        # Sort tags by specificity priority (hentai→ecchi→kids→anime)
        sorted_tags = sorted(
            tags_by_label.items(),
            key=lambda t: get_category_priority(t[0]),
        )
        for tag_label, tag_id in sorted_tags:
            folder = match_folder(tag_label, folders)
            if not folder:
                continue

            if matches_any(tag_label, HENTAI_KEYWORDS):
                rules.append(make_rule(
                    name=f"Hentai → {inst_name}", media_type=media_type,
                    target=inst_name, root_folder=folder, qp=default_qp,
                    tags=[tag_id], series_type="anime",
                    keyword_include=HENTAI_TMDB_KEYWORDS, order=order))
                order += 1
            elif matches_any(tag_label, ECCHI_KEYWORDS):
                rules.append(make_rule(
                    name=f"Ecchi → {inst_name}", media_type=media_type,
                    target=inst_name, root_folder=folder, qp=default_qp,
                    tags=[tag_id], series_type="anime",
                    keyword_include=ECCHI_TMDB_KEYWORDS, order=order))
                order += 1
            elif matches_any(tag_label, KIDS_KEYWORDS):
                rules.append(make_rule(
                    name=f"Kids → {inst_name}", media_type=media_type,
                    target=inst_name, root_folder=folder, qp=default_qp,
                    tags=[tag_id], genre_include=KIDS_GENRES, order=order))
                order += 1
                rules.append(make_rule(
                    name=f"Kids (keywords) → {inst_name}", media_type=media_type,
                    target=inst_name, root_folder=folder, qp=default_qp,
                    tags=[tag_id], keyword_include=KIDS_TMDB_KEYWORDS, order=order))
                order += 1
            elif matches_any(tag_label, ANIME_KEYWORDS):
                rules.append(make_rule(
                    name=f"Anime → {inst_name}", media_type=media_type,
                    target=inst_name, root_folder=folder, qp=default_qp,
                    tags=[tag_id], series_type="anime",
                    keyword_include=ANIME_TMDB_KEYWORDS, order=order))
                order += 1

        # Scan folder names for categories not yet covered by tags
        for folder in folders:
            fname = folder.rsplit("/", 1)[-1].lower() if "/" in folder else folder.lower()
            if matches_any(fname, KIDS_KEYWORDS) and not has_rule_for(rules, folder):
                dtags = get_default_tags(tags_by_label, media_type)
                rules.append(make_rule(
                    name=f"Kids ({fname}) → {inst_name}", media_type=media_type,
                    target=inst_name, root_folder=folder, qp=default_qp,
                    tags=dtags, genre_include=KIDS_GENRES, order=order))
                order += 1

    # Sort by specificity order, strip internal field
    rules.sort(key=lambda r: r.get("_order", 999))
    for r in rules:
        r.pop("_order", None)

    # Add catchall rules from default instances
    seen_catchalls = set()
    for inst_name, inst in analysis.items():
        default_for = inst.get("is_default_for")
        if not default_for or default_for in seen_catchalls:
            continue
        media_type = default_for if default_for == "movie" else "tv"
        default_qp = inst["quality_profiles"][0]["id"] if inst["quality_profiles"] else 1
        tags_by_label = {t["label"].lower(): t["id"] for t in inst["tags"]}
        dtags = get_default_tags(tags_by_label, media_type)
        dfolder = get_default_folder(inst["root_folders"], media_type)
        if dfolder:
            rules.append({
                "name": f"All Other {'Movies' if media_type == 'movie' else 'TV'}",
                "media_type": media_type, "target": inst_name,
                "root_folder": dfolder, "quality_profile_id": default_qp,
                "tags": dtags, "is_catchall": True, "series_type": "standard",
            })
            seen_catchalls.add(default_for)

    logger.info(f"Heuristic generated {len(rules)} routing rules")
    return rules
