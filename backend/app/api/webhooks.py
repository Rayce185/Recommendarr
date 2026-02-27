"""Webhook receivers for real-time event ingestion."""

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


@router.post("/webhook/tautulli")
async def tautulli_webhook(request: Request):
    """Tautulli sends play/stop/pause/resume events here.
    
    Configure in Tautulli: Settings → Notification Agents → Webhook
    URL: http://<recommendarr>:30800/api/v1/webhook/tautulli
    """
    body = await request.json()
    event_type = body.get("event_type", "unknown")
    # TODO: parse Tautulli payload, update watch_history, trigger profile refresh
    return {"status": "received", "event_type": event_type}


@router.post("/webhook/radarr")
async def radarr_webhook(request: Request):
    """Radarr sends grab/download/rename events here."""
    body = await request.json()
    event_type = body.get("eventType", "unknown")
    # TODO: update availability_alerts, auto_grab_log
    return {"status": "received", "event_type": event_type}


@router.post("/webhook/sonarr")
async def sonarr_webhook(request: Request):
    """Sonarr sends grab/download/rename events here."""
    body = await request.json()
    event_type = body.get("eventType", "unknown")
    # TODO: update availability_alerts
    return {"status": "received", "event_type": event_type}
