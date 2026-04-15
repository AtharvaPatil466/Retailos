"""Structured logging configuration for RetailOS."""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
store_id_var: ContextVar[str] = ContextVar("store_id", default="")
_BASE_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _BASE_LOG_RECORD_FIELDS and not key.startswith("_")
    }


def _merge_runtime_context(_logger, _method_name, event_dict: dict[str, Any]) -> dict[str, Any]:
    if req_id := request_id_var.get(""):
        event_dict.setdefault("request_id", req_id)
    if user_id := user_id_var.get(""):
        event_dict.setdefault("user_id", user_id)
    if store_id := store_id_var.get(""):
        event_dict.setdefault("store_id", store_id)
    return event_dict


def _add_record_metadata(_logger, _method_name, event_dict: dict[str, Any]) -> dict[str, Any]:
    record = event_dict.get("_record")
    if not record:
        return event_dict

    event_dict.setdefault("module", record.module)
    event_dict.setdefault("function", record.funcName)
    event_dict.setdefault("line", record.lineno)

    for key, value in _extra_fields(record).items():
        event_dict.setdefault(key, value)

    return event_dict


def _try_import_structlog():
    try:
        import structlog
    except ImportError:
        return None
    return structlog


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        log_entry.update(_merge_runtime_context(None, "", {}))
        log_entry.update(_extra_fields(record))

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        req_id = request_id_var.get("")
        prefix = f"[{req_id[:8]}] " if req_id else ""
        extras = " ".join(f"{key}={value}" for key, value in _extra_fields(record).items())
        suffix = f" {extras}" if extras else ""
        return f"{color}{record.levelname:8}{self.RESET} {prefix}{record.name}: {record.getMessage()}{suffix}"


def bind_request_context(
    request_id: str = "",
    user_id: str = "",
    store_id: str = "",
) -> None:
    request_id_var.set(request_id)
    user_id_var.set(user_id)
    store_id_var.set(store_id)

    if structlog := _try_import_structlog():
        structlog.contextvars.clear_contextvars()
        payload = {key: value for key, value in {
            "request_id": request_id,
            "user_id": user_id,
            "store_id": store_id,
        }.items() if value}
        if payload:
            structlog.contextvars.bind_contextvars(**payload)


def clear_request_context() -> None:
    bind_request_context()
    if structlog := _try_import_structlog():
        structlog.contextvars.clear_contextvars()


def setup_logging(
    level: str | None = None,
    json_format: bool | None = None,
) -> None:
    log_level = level or os.environ.get("LOG_LEVEL", "INFO")
    default_format = "json" if os.environ.get("RETAILOS_ENV", os.environ.get("ENV", "")).lower() == "production" else "human"
    use_json = json_format if json_format is not None else os.environ.get("LOG_FORMAT", default_format) == "json"

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    structlog = _try_import_structlog()
    if structlog:
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            _merge_runtime_context,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            _add_record_metadata,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        renderer = structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=renderer,
                foreign_pre_chain=shared_processors,
            )
        )
        structlog.configure(
            processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        handler.setFormatter(JSONFormatter() if use_json else HumanFormatter())

    root.addHandler(handler)

    for lib in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    logging.getLogger("retailos").info(
        "Logging configured",
        extra={"log_level": log_level.upper(), "log_format": "json" if use_json else "human"},
    )


def generate_request_id() -> str:
    """Generate a unique request ID for correlation."""
    return str(uuid.uuid4())
