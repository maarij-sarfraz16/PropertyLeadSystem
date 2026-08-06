"""Structured logging.

Every pipeline stage logs one event with a stable `event` name plus context fields, so the
run can be traced (or shipped to a log aggregator) without parsing prose:

    scan.started / scan.fetched / listing.new / listing.duplicate /
    extraction.completed / lead.saved / dashboard.updated / scan.error

Text mode (default) is readable in a terminal; `LOG_JSON=true` emits newline-delimited JSON
for production log shipping.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.config import get_settings

# LogRecord attributes that are not caller-supplied context.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}

_configured = False


class _JsonFormatter(logging.Formatter):
    """Newline-delimited JSON, one object per record, with `extra=` fields inlined."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ContextFormatter(logging.Formatter):
    """Human-readable line with `extra=` fields appended as key=value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        if context:
            rendered = " ".join(f"{key}={value}" for key, value in context.items())
            return f"{base} | {rendered}"
        return base


def configure_logging(force: bool = False) -> None:
    """Install the root handler once. Safe to call from any entry point."""
    global _configured
    if _configured and not force:
        return

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            _ContextFormatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")
        )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # httpx logs every scrape request at INFO; that is noise at a 30s cadence.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
