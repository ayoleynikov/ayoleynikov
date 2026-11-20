"""Structured JSON logging for Pulse services."""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from pulse.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure root logger to emit structured JSON to stdout."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
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
