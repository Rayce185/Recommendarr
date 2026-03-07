"""Collaborative filtering for taste-based recommendations.

Finds users with similar watch patterns (Jaccard similarity on
watched item sets) and suggests items watched by similar peers
but not yet seen by the target user.
"""

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


async def get_collaborative_peers(
    tautulli: Any,
    username: str,
    limit: int = 5,
) -> list[tuple[str, float]]:
    """Find users with similar taste based on watch overlap.

    Uses Jaccard similarity on item_key sets. Minimum 3 shared items
    required for a peer to qualify.

    Args:
        tautulli: TautulliClient instance
        username: Target user's Tautulli username
        limit: Max peers to return

    Returns:
        List of (username, similarity_score) pairs, sorted by similarity desc.
    """
    # Get all history (unfiltered) to compare across users
    all_history = await tautulli.get_history(user_id=None, limit=10000)
    user_items = {e.item_key for e in all_history if e.user_id == username}

    if not user_items:
        return []

    # Group all history by user
    by_user: dict[str, set] = defaultdict(set)
    for event in all_history:
        if event.user_id != username:
            by_user[event.user_id].add(event.item_key)

    # Jaccard similarity
    peers = []
    for other_user, other_items in by_user.items():
        intersection = len(user_items & other_items)
        union = len(user_items | other_items)
        if union > 0 and intersection >= 3:
            similarity = intersection / union
            peers.append((other_user, round(similarity, 3)))

    peers.sort(key=lambda x: x[1], reverse=True)
    return peers[:limit]


async def get_collaborative_suggestions(
    tautulli: Any,
    username: str,
    known_item_keys: set[str],
    limit: int = 20,
) -> list[tuple[str, float, str]]:
    """Get items watched by similar users but not by this user.

    Scores each candidate by accumulated peer similarity weighted by
    the peer's completion percentage for that item.

    Args:
        tautulli: TautulliClient instance
        username: Target user's Tautulli username
        known_item_keys: Set of item_keys the user has already watched
        limit: Max suggestions to return

    Returns:
        List of (item_key, peer_score, peer_username) tuples, sorted by score desc.
    """
    peers = await get_collaborative_peers(tautulli, username, limit=10)
    if not peers:
        return []

    suggestions: dict[str, tuple[float, str]] = {}
    all_history = await tautulli.get_history(user_id=None, limit=10000)

    for peer_name, similarity in peers:
        peer_events = [e for e in all_history if e.user_id == peer_name]
        for event in peer_events:
            if event.item_key not in known_item_keys and event.completion_pct >= 70:
                key = event.item_key
                existing_score = suggestions.get(key, (0.0, ""))[0]
                new_score = existing_score + similarity * (event.completion_pct / 100)
                if new_score > existing_score:
                    suggestions[key] = (new_score, peer_name)

    results = [(key, score, peer) for key, (score, peer) in suggestions.items()]
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]
