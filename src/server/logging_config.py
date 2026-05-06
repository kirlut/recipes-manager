"""Structured JSON logging to stdout via stdlib `logging`.

Configured once at startup by `configure_logging(level)`. Every record
becomes one JSON object per line on stdout. Extras passed via
`logger.info(msg, extra={...})` are merged into the top-level object,
shadowing the standard fields if they collide.
"""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone

_STD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": "logging_config.JsonFormatter"},
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["stdout"], "level": level.upper(), "propagate": False},
                "uvicorn.error": {"handlers": ["stdout"], "level": level.upper(), "propagate": False},
                "uvicorn.access": {"handlers": ["stdout"], "level": level.upper(), "propagate": False},
            },
            "root": {"handlers": ["stdout"], "level": level.upper()},
        }
    )
