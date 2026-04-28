from __future__ import annotations

import json
import logging

from app.logging_config import JsonLogFormatter


def test_json_log_formatter_emits_structured_payload() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Hello %s",
        args=("world",),
        exc_info=None,
    )
    record.user_id = 42  # type: ignore[attr-defined]

    payload = json.loads(formatter.format(record))

    assert payload["logger"] == "app.test"
    assert payload["level"] == "INFO"
    assert payload["message"] == "Hello world"
    assert payload["user_id"] == 42
    assert "timestamp" in payload