"""Structured JSON logging with request correlation.

Replaces basicConfig with machine-parseable JSON output.
Adds request-ID middleware for tracing requests across log lines.
"""

import logging
import os
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ── Context var for request correlation ──────────────────────────

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


# ── JSON Formatter ───────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter.
    
    Output: {"ts": "...", "level": "...", "logger": "...", "msg": "...", "request_id": "..."}
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get("-"),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Extra fields passed via logger.info("msg", extra={"key": "val"})
        for key in ("user", "method", "path", "status", "duration_ms", "ip"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


# ── Request ID Middleware ────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request for log correlation."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_var.set(rid)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        # Log completed requests (skip health checks to reduce noise)
        if not request.url.path.endswith("/health"):
            access_logger = logging.getLogger("recommendarr.access")
            access_logger.info(
                "%s %s → %s (%.1fms)",
                request.method, request.url.path, response.status_code, duration_ms,
                extra={
                    "method": request.method,
                    "path": str(request.url.path),
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "ip": request.headers.get("x-forwarded-for", request.client.host if request.client else "-"),
                },
            )

        response.headers["x-request-id"] = rid
        return response


# ── Setup ────────────────────────────────────────────────────────

def setup_logging(log_level: str = "INFO"):
    """Configure structured JSON logging for the application."""
    use_json = os.getenv("LOG_FORMAT", "json").lower() == "json"

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler()
    if use_json:
        handler.setFormatter(JSONFormatter())
    else:
        # Fallback plain-text for local dev
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root.addHandler(handler)

    # Quiet noisy libraries
    for noisy in ("httpx", "httpcore", "uvicorn.access", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging configured: format=%s, level=%s",
                                     "json" if use_json else "plain", log_level)
