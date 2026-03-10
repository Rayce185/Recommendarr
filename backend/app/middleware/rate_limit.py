"""API rate limiting via slowapi.

Global per-IP limits with stricter caps on auth and AI endpoints.
Configurable via RATE_LIMIT_DEFAULT env var (default: 60/minute).
"""

import logging
import os

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

# Default: 60 requests/minute per IP
DEFAULT_RATE = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")

# Stricter limits for expensive endpoints
AUTH_RATE = os.getenv("RATE_LIMIT_AUTH", "10/minute")
AI_RATE = os.getenv("RATE_LIMIT_AI", "10/minute")
RECOMMENDATION_RATE = os.getenv("RATE_LIMIT_RECS", "20/minute")


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in the chain is the real client
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# ── Limiter instance ────────────────────────────────────────────

limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[DEFAULT_RATE],
    storage_uri="memory://",
    strategy="fixed-window",
)


def setup_rate_limiting(app):
    """Wire rate limiting into a FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("Rate limiting enabled: default=%s, auth=%s, ai=%s, recs=%s",
                DEFAULT_RATE, AUTH_RATE, AI_RATE, RECOMMENDATION_RATE)
