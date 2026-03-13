"""Plex OAuth — aligned with Overseerr's proven implementation.

Flow (matches Overseerr):
  1. Frontend creates PIN directly on plex.tv
  2. Frontend polls plex.tv directly for token
  3. Frontend sends authToken to backend POST /auth/plex
  4. Backend validates token via plex.tv/users/account.json
  5. Backend checks server access via plex.tv/api/users (XML)
  6. Backend issues JWT
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PlexUser:
    """Authenticated Plex user identity."""
    plex_user_id: int
    username: str
    email: str
    thumb: str
    plex_token: str
    is_server_owner: bool = False


async def get_plex_user(auth_token: str) -> PlexUser:
    """Fetch user identity from plex.tv using their auth token.

    Uses /users/account.json — same endpoint as Overseerr.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://plex.tv/users/account.json",
            headers={"X-Plex-Token": auth_token, "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    user_data = data.get("user", data)
    return PlexUser(
        plex_user_id=user_data["id"],
        username=user_data.get("username") or user_data.get("title", "Unknown"),
        email=user_data.get("email", ""),
        thumb=user_data.get("thumb", ""),
        plex_token=auth_token,
    )


async def check_server_access(
    user: PlexUser,
    admin_token: str,
    machine_id: str,
) -> bool:
    """Check if the Plex user has access to the configured server.

    Uses plex.tv/api/users (XML) — same endpoint as Overseerr.
    Matches user by plexId, then checks if their Server entries
    contain our machineIdentifier.

    The server owner (admin) always has access — matched by plexId
    comparison against the admin account.
    """
    # ── Step 1: Check if user is the server owner ────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://plex.tv/users/account.json",
                headers={"X-Plex-Token": admin_token, "Accept": "application/json"},
            )
            if resp.status_code == 200:
                admin_data = resp.json().get("user", resp.json())
                admin_plex_id = admin_data.get("id")
                if admin_plex_id and admin_plex_id == user.plex_user_id:
                    logger.info(f"User {user.username} is the server owner (plexId match)")
                    user.is_server_owner = True
                    return True
                # Also match by email (Overseerr fallback)
                admin_email = (admin_data.get("email") or "").lower()
                if admin_email and admin_email == user.email.lower():
                    logger.info(f"User {user.username} is the server owner (email match)")
                    user.is_server_owner = True
                    return True
    except Exception as e:
        logger.warning(f"Admin identity check failed: {e}")

    # ── Step 2: Check shared users via plex.tv/api/users (XML) ───
    # This is the same endpoint Overseerr uses in checkUserAccess()
    if not machine_id:
        logger.error("Plex machine_id not configured — cannot check user access")
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://plex.tv/api/users",
                headers={
                    "X-Plex-Token": admin_token,
                    "Accept": "application/xml",
                },
            )
            if resp.status_code != 200:
                logger.error(f"plex.tv /api/users returned {resp.status_code}")
                return False

            root = ET.fromstring(resp.text)

            for user_el in root.findall(".//User"):
                uid = user_el.get("id", "")
                if str(user.plex_user_id) != uid:
                    continue

                # Found the user — now check if they have access to our server
                for server_el in user_el.findall(".//Server"):
                    srv_machine_id = server_el.get("machineIdentifier", "")
                    if srv_machine_id == machine_id:
                        logger.info(
                            f"User {user.username} (id={uid}) has access to server {machine_id[:12]}..."
                        )
                        return True

                # User exists but doesn't have our server
                logger.warning(
                    f"User {user.username} (id={uid}) found but has no access to server {machine_id[:12]}..."
                )
                return False

    except Exception as e:
        logger.error(f"Shared users check failed: {e}")
        return False

    logger.warning(f"User {user.username} (id={user.plex_user_id}) not found in shared users")
    return False
