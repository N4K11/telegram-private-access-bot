from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.config import dictConfig

from app.runtime_state import record_critical_error, record_telegram_api_error
from app.services.observability import (
    EVENT_CRITICAL_ERROR,
    EVENT_TELEGRAM_API_ERROR,
    EVENT_WORKER_CYCLE_FAILED,
    emit_critical_error_webhook,
    sanitize_observability_payload,
    sanitize_observability_text,
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _RESERVED_LOG_RECORD_KEYS:
                continue
            payload[key] = value
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(
            sanitize_observability_payload(payload),
            ensure_ascii=False,
            default=str,
        )


class RuntimeObservabilityHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        message = sanitize_observability_text(record.getMessage())
        event_name = _infer_event_name(record, message)
        if event_name == EVENT_TELEGRAM_API_ERROR:
            record_telegram_api_error(message)
        record_critical_error(event_name, message, source=record.name)


class CriticalErrorWebhookHandler(logging.Handler):
    def __init__(self, *, webhook_url: str, level: int = logging.ERROR) -> None:
        super().__init__(level=level)
        self.webhook_url = webhook_url

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR or not self.webhook_url:
            return
        message = sanitize_observability_text(record.getMessage())
        emit_critical_error_webhook(
            self.webhook_url,
            event_name=_infer_event_name(record, message),
            source=record.name,
            message=message,
            occurred_at=datetime.now(UTC),
        )


_RESERVED_LOG_RECORD_KEYS = {
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
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def configure_logging(
    level: str = "INFO",
    *,
    critical_error_webhook_url: str | None = None,
) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": JsonLogFormatter,
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "level": level.upper(),
                }
            },
            "root": {"handlers": ["console"], "level": level.upper()},
        }
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(RuntimeObservabilityHandler(level=logging.ERROR))
    if critical_error_webhook_url:
        root_logger.addHandler(
            CriticalErrorWebhookHandler(
                webhook_url=critical_error_webhook_url,
                level=logging.ERROR,
            )
        )
    logging.getLogger(__name__).debug("Logging configured.")


def _infer_event_name(record: logging.LogRecord, message: str) -> str:
    explicit = getattr(record, "event_name", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    exc = record.exc_info[1] if record.exc_info else None
    if exc is not None and _looks_like_telegram_exception(exc):
        return EVENT_TELEGRAM_API_ERROR

    if record.name.startswith("aiogram") and "telegram" in message.lower():
        return EVENT_TELEGRAM_API_ERROR

    if "worker cycle failed" in message.lower():
        return EVENT_WORKER_CYCLE_FAILED

    return EVENT_CRITICAL_ERROR


def _looks_like_telegram_exception(exc: BaseException) -> bool:
    module_name = exc.__class__.__module__.lower()
    class_name = exc.__class__.__name__.lower()
    return "telegram" in module_name or class_name.startswith("telegram")