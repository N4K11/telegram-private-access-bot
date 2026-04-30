from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.config import dictConfig

from app.runtime_state import record_telegram_api_error


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
        return json.dumps(payload, ensure_ascii=False, default=str)


class TelegramApiErrorCaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None and _looks_like_telegram_exception(exc):
            record_telegram_api_error(f"{exc.__class__.__name__}: {exc}")
            return

        message = record.getMessage()
        if record.name.startswith("aiogram") and "telegram" in message.lower():
            record_telegram_api_error(message)


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


def configure_logging(level: str = "INFO") -> None:
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
    if not any(
        isinstance(handler, TelegramApiErrorCaptureHandler)
        for handler in root_logger.handlers
    ):
        runtime_handler = TelegramApiErrorCaptureHandler(level=logging.ERROR)
        root_logger.addHandler(runtime_handler)
    logging.getLogger(__name__).debug("Logging configured.")


def _looks_like_telegram_exception(exc: BaseException) -> bool:
    module_name = exc.__class__.__module__.lower()
    class_name = exc.__class__.__name__.lower()
    return "telegram" in module_name or class_name.startswith("telegram")
