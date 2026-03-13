"""Structured logging — JSON formatter + request-context enrichment.

Non-invasive: existing `logger.info("msg")` calls keep working.
The formatter intercepts at output time, injecting request context
(request_id, user, method, path) from the ContextVar set by middleware.

Toggle via LOG_FORMAT env var:
  - "json"  → machine-readable JSON lines (default in production)
  - "text"  → human-readable coloured output (default when DEBUG=true)
"""

import json
import logging
import sys
from datetime import datetime, timezone

from app.middleware.request_context import get_request_context


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line.

    Schema:
        {
            "ts": "2026-03-13T14:22:01.123Z",
            "level": "INFO",
            "logger": "app.api.auth",
            "msg": "Login successful: alice",
            "request_id": "abc123",
            "user": "alice",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "exc": "Traceback ...",          # only on exception
        }
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Inject request context if available
        ctx = get_request_context()
        if ctx:
            entry.update(ctx)

        # Exception info
        if record.exc_info and record.exc_info[1]:
            entry["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exc"] = record.exc_text

        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable format with optional request context.

    Output:
        2026-03-13 14:22:01 [INFO] app.api.auth: Login successful: alice  [req=abc123 user=alice POST /api/v1/auth/login]
    """

    LEVEL_COLOURS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def __init__(self, use_colour: bool = True):
        super().__init__()
        self.use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname
        if self.use_colour:
            colour = self.LEVEL_COLOURS.get(level, "")
            level_str = f"{colour}{level:<8}{self.RESET}"
        else:
            level_str = f"{level:<8}"

        msg = record.getMessage()
        line = f"{ts} [{level_str}] {record.name}: {msg}"

        # Append request context inline
        ctx = get_request_context()
        if ctx:
            parts = []
            if ctx.get("request_id"):
                parts.append(f"req={ctx['request_id'][:8]}")
            if ctx.get("user"):
                parts.append(f"user={ctx['user']}")
            if ctx.get("method"):
                parts.append(ctx["method"])
            if ctx.get("path"):
                parts.append(ctx["path"])
            if parts:
                ctx_str = " ".join(parts)
                if self.use_colour:
                    line += f"  \033[2m[{ctx_str}]\033[0m"
                else:
                    line += f"  [{ctx_str}]"

        # Exception info
        if record.exc_info and record.exc_info[1]:
            line += "\n" + self.formatException(record.exc_info)
        elif record.exc_text:
            line += "\n" + record.exc_text

        return line


def setup_logging(log_level: str = "INFO", log_format: str = "auto", debug: bool = False):
    """Configure root logger with structured formatter.

    Args:
        log_level:  Python log level name (DEBUG, INFO, WARNING, ERROR).
        log_format: "json", "text", or "auto" (json unless debug=True).
        debug:      App debug flag — used for auto-detection.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Resolve format
    if log_format == "auto":
        fmt = "text" if debug else "json"
    else:
        fmt = log_format.lower()

    # Build handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        # Detect TTY for colour support
        use_colour = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        handler.setFormatter(TextFormatter(use_colour=use_colour))

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(level)
    # Remove any existing handlers (prevents duplicate output)
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("recommendarr").info(
        f"Logging configured: level={log_level.upper()} format={fmt}"
    )
