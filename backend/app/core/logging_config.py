import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging_context import ContextLogFilter

_RESERVED_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "message",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line — timestamp, level, logger name, message,
    and whichever correlation IDs (request_id/workspace_id/call_id) are
    bound for this log call (see logging_context.py), plus any extra
    fields passed via `logger.info(..., extra={...})`. Machine-parseable
    for log aggregation, unlike the human-oriented text format used when
    LOG_FORMAT=text (e.g. local dev)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "workspace_id", "call_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload and not key.startswith("_"):
                try:
                    json.dumps(value)
                except TypeError:
                    value = str(value)
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(ContextLogFilter())

    if settings.log_format.lower() == "text":
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | request_id=%(request_id)s workspace_id=%(workspace_id)s "
                "call_id=%(call_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers = [handler]
