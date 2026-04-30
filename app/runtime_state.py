from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from threading import Lock

from app.utils.datetime import ensure_aware_utc, utcnow


@dataclass(frozen=True, slots=True)
class RuntimeStateSnapshot:
    started_at: datetime | None = None
    last_update_id: int | None = None
    last_update_kind: str | None = None
    last_update_at: datetime | None = None
    last_maintenance_run_at: datetime | None = None
    last_maintenance_label: str | None = None
    last_telegram_api_error_at: datetime | None = None
    last_telegram_api_error: str | None = None


_state = RuntimeStateSnapshot()
_lock = Lock()


def reset_runtime_state() -> None:
    global _state
    with _lock:
        _state = RuntimeStateSnapshot()


def mark_started(*, now: datetime | None = None) -> None:
    global _state
    with _lock:
        _state = replace(_state, started_at=ensure_aware_utc(now or utcnow()))


def record_update(
    *,
    update_id: int | None = None,
    kind: str | None = None,
    at: datetime | None = None,
) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            last_update_id=update_id if update_id is not None else _state.last_update_id,
            last_update_kind=kind or _state.last_update_kind,
            last_update_at=ensure_aware_utc(at or utcnow()),
        )


def record_maintenance_run(*, label: str, at: datetime | None = None) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            last_maintenance_run_at=ensure_aware_utc(at or utcnow()),
            last_maintenance_label=label,
        )


def record_telegram_api_error(message: str, *, at: datetime | None = None) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            last_telegram_api_error_at=ensure_aware_utc(at or utcnow()),
            last_telegram_api_error=message.strip(),
        )


def snapshot_runtime_state() -> RuntimeStateSnapshot:
    with _lock:
        return replace(_state)
