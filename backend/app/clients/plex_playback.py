"""Plex device enumeration and playback control.

Standalone async functions for discovering Plex player devices and
initiating remote playback via the server-as-controller pattern.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


async def get_player_devices(token: str) -> list[dict]:
    """Get available Plex player devices (clients that can play media).

    Returns list of player devices with name, product, clientId, connections.
    """
    devices = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://plex.tv/api/v2/resources",
                params={
                    "X-Plex-Token": token,
                    "includeHttps": 1,
                    "includeRelay": 1,
                },
                headers={
                    "Accept": "application/json",
                    "X-Plex-Client-Identifier": "recommendarr",
                },
            )
            r.raise_for_status()
            data = r.json()
            for res in data:
                provides = res.get("provides", "")
                if "player" not in provides:
                    continue
                conns = res.get("connections", [])
                local_conn = next((c for c in conns if c.get("local")), None)
                best_conn = local_conn or (conns[0] if conns else None)
                devices.append({
                    "client_id": res.get("clientIdentifier", ""),
                    "name": res.get("name", "Unknown"),
                    "product": res.get("product", ""),
                    "platform": res.get("platform", ""),
                    "provides": provides,
                    "connection_uri": best_conn.get("uri") if best_conn else None,
                    "owned": res.get("owned", False),
                    "last_seen": res.get("lastSeenAt"),
                })
    except Exception as e:
        logger.error(f"Plex resources fetch failed: {e}")
    return devices


async def play_on_device(
    rating_key: int,
    client_id: str,
    server_url: str,
    machine_id: str,
    token: str,
) -> dict:
    """Initiate playback of a media item on a specific Plex player.

    Uses Plex playQueues + commandManager to start playback on the target device.
    The server acts as controller, sending the play command to the client.

    Returns: {"success": bool, "message": str}
    """
    try:
        # Step 1: Create a play queue on the server
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{server_url}/playQueues",
                params={
                    "type": "video",
                    "uri": f"server://{machine_id}/com.plexapp.plugins.library/library/metadata/{rating_key}",
                    "shuffle": 0, "repeat": 0, "continuous": 0, "own": 1,
                    "X-Plex-Token": token,
                    "X-Plex-Client-Identifier": "recommendarr",
                },
                headers={"Accept": "application/json"},
            )
            if r.status_code not in (200, 201):
                return {"success": False, "message": f"Failed to create play queue: HTTP {r.status_code}"}
            pq = r.json()
            pq_id = pq.get("MediaContainer", {}).get("playQueueID")
            if not pq_id:
                return {"success": False, "message": "No playQueueID returned"}

        # Step 2: Send playMedia command to the target device via server
        address = server_url.split("://")[1].split(":")[0]
        port = server_url.split(":")[-1]
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{server_url}/player/playback/playMedia",
                params={
                    "key": f"/library/metadata/{rating_key}",
                    "machineIdentifier": machine_id,
                    "address": address, "port": port, "protocol": "http",
                    "containerKey": f"/playQueues/{pq_id}?own=1&window=200",
                    "commandID": 1, "type": "video",
                    "X-Plex-Token": token,
                    "X-Plex-Target-Client-Identifier": client_id,
                },
                headers={
                    "X-Plex-Client-Identifier": "recommendarr",
                    "X-Plex-Target-Client-Identifier": client_id,
                },
            )
            if r.status_code == 200:
                return {"success": True, "message": f"Playback started (queue {pq_id})"}
            return {"success": False, "message": f"Player command failed: HTTP {r.status_code} - {r.text[:200]}"}

    except httpx.ConnectError:
        return {"success": False, "message": "Cannot reach device — it may be offline"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}
