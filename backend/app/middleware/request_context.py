"""Request context middleware — injects correlation data into logging.

Uses contextvars so any logger in the call chain automatically picks up
request_id, user, method, and path without explicit passing.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── Context storage ──────────────────────────────────────────────

_request_context: ContextVar[Optional[dict]] = ContextVar(
    "request_context", default=None
)


def get_request_context() -> Optional[dict]:
    """Read current request context (called by log formatters)."""
    return _request_context.get()


# ── Middleware ────────────────────────────────────────────────────

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate request context for structured logging.

    Sets:
        request_id  — X-Request-ID header or generated UUID4 (first 12 chars)
        method      — HTTP method
        path        — request path
        user        — extracted from JWT sub claim if present

    Also sets X-Request-ID on the response for traceability.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(
            "x-request-id", uuid.uuid4().hex[:12]
        )

        # Extract username from JWT if available (best-effort, no validation)
        user = self._extract_user(request)

        ctx = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        if user:
            ctx["user"] = user

        token = _request_context.set(ctx)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _request_context.reset(token)

    @staticmethod
    def _extract_user(request: Request) -> Optional[str]:
        """Best-effort JWT sub extraction — no crypto, just peek at payload."""
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            import base64
            parts = auth[7:].split(".")
            if len(parts) < 2:
                return None
            payload = parts[1]
            payload += "=" * (4 - len(payload) % 4)
            import json
            data = json.loads(base64.urlsafe_b64decode(payload))
            return data.get("sub")
        except Exception:
            return None
