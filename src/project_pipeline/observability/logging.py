from __future__ import annotations

import importlib
import json
import logging
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

from pydantic import SecretBytes, SecretStr

from project_pipeline.configuration.models import LogFormat, LoggingSettings
from project_pipeline.observability.context import current_context

_get_current_span: Any | None
try:
    _trace_module = importlib.import_module("opentelemetry.trace")
    _get_current_span = getattr(_trace_module, "get_current_span", None)
except ImportError:
    _get_current_span = None

REDACTED_VALUE = "<redacted>"
_STANDARD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def _sensitive(key: str, redacted_fields: frozenset[str]) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in redacted_fields)


def sanitize(value: Any, redacted_fields: frozenset[str], key: str = "") -> Any:
    if _sensitive(key, redacted_fields) or isinstance(value, (SecretStr, SecretBytes)):
        return REDACTED_VALUE
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize(item_value, redacted_fields, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize(item, redacted_fields, key) for item in value]
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "message": str(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _trace_attributes() -> dict[str, str]:
    if _get_current_span is None:
        return {}
    span_context = _get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": format(span_context.trace_id, "032x"),
        "span_id": format(span_context.span_id, "016x"),
    }


class StructuredFormatter(logging.Formatter):
    def __init__(self, settings: LoggingSettings) -> None:
        super().__init__()
        self.settings = settings
        self.redacted_fields = frozenset(item.lower() for item in settings.redacted_fields)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "service": self.settings.service_name,
            "logger": record.name,
            "event": record.getMessage(),
            **current_context().as_attributes(),
            **_trace_attributes(),
        }
        if self.settings.include_process:
            payload["process_id"] = record.process
        if self.settings.include_thread:
            payload["thread_id"] = record.thread
            payload["thread_name"] = record.threadName
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_FIELDS and not key.startswith("_")
        }
        if extras:
            payload["attributes"] = sanitize(extras, self.redacted_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if self.settings.include_source:
            payload["source"] = {
                "file": record.pathname,
                "function": record.funcName,
                "line": record.lineno,
            }
        if self.settings.format is LogFormat.JSON:
            return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        correlation = payload.get("correlation_id", "-")
        return (
            f"{payload['timestamp_utc']} {record.levelname} {record.name} "
            f"[{correlation}] {record.getMessage()}"
        )


def configure_logging(
    settings: LoggingSettings,
    *,
    stream: TextIO | None = None,
    force: bool = True,
) -> logging.Logger:
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(StructuredFormatter(settings))
    root = logging.getLogger()
    if force:
        root.handlers.clear()
    root.setLevel(getattr(logging, settings.level))
    root.addHandler(handler)
    logging.captureWarnings(True)
    return logging.getLogger(settings.service_name)


def log_event(logger: logging.Logger, level: int, event: str, **attributes: Any) -> None:
    logger.log(level, event, extra=attributes)
