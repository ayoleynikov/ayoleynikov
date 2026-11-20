"""Structured JSON logging for Pulse services — secrets never appear in logs."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from pulse.config import Settings

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|credential|private[_-]?key)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def redact_secrets(value: Any) -> Any:
    """Recursively redact secret-looking keys from structured log payloads."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                out[key] = _REDACTED
            else:
                out[key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str) and _looks_like_secret_assignment(value):
        return _redact_assignment_string(value)
    return value


def _looks_like_secret_assignment(text: str) -> bool:
    return bool(
        re.search(
            r"(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]",
            text,
            re.IGNORECASE,
        )
    )


def _redact_assignment_string(text: str) -> str:
    return re.sub(
        r"((?:password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*)(\S+)",
        rf"\1{_REDACTED}",
        text,
        flags=re.IGNORECASE,
    )


class SecretRedactingFilter(logging.Filter):
    """Strip secrets from LogRecord extras and message args before emit."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = redact_secrets(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_secrets(arg) for arg in record.args)

        # python-json-logger merges non-standard attributes into the JSON payload.
        for key, value in list(record.__dict__.items()):
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
                "taskName",
            }:
                continue
            if _SECRET_KEY_RE.search(key):
                setattr(record, key, _REDACTED)
            else:
                setattr(record, key, redact_secrets(value))

        if isinstance(record.msg, str) and _looks_like_secret_assignment(record.msg):
            record.msg = _redact_assignment_string(record.msg)
        return True


def configure_logging(settings: Settings) -> None:
    """Configure root logger to emit structured JSON to stdout."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SecretRedactingFilter())
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy third-party loggers in production-ish defaults.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.debug else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
