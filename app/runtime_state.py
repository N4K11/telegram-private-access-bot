from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from threading import Lock

from app.utils.datetime import ensure_aware_utc, utcnow

MAX_RECENT_CRITICAL_ERRORS = 20


@dataclass(frozen=True, slots=True)
class CriticalErrorRecord:
    event_name: str
    source: str
    message: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class WorkerStatusRecord:
    name: str
    status: str
    details: str | None
    updated_at: datetime


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
    last_crypto_reconcile_at: datetime | None = None
    last_crypto_reconcile_processed_count: int | None = None
    last_crypto_reconcile_paid_count: int | None = None
    last_crypto_reconcile_expired_count: int | None = None
    last_crypto_reconcile_active_invoice_count: int | None = None
    last_crypto_reconcile_error_at: datetime | None = None
    last_crypto_reconcile_error: str | None = None
    recent_critical_errors: tuple[CriticalErrorRecord, ...] = ()
    worker_statuses: tuple[WorkerStatusRecord, ...] = ()
    last_backup_result_at: datetime | None = None
    last_backup_result_status: str | None = None
    last_backup_result_details: str | None = None


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


def record_critical_error(
    event_name: str,
    message: str,
    *,
    source: str,
    at: datetime | None = None,
) -> None:
    global _state
    occurred_at = ensure_aware_utc(at or utcnow())
    entry = CriticalErrorRecord(
        event_name=event_name.strip() or "critical_error",
        source=source.strip() or "runtime",
        message=message.strip() or "unknown error",
        occurred_at=occurred_at,
    )
    with _lock:
        recent = (entry, *_state.recent_critical_errors[: MAX_RECENT_CRITICAL_ERRORS - 1])
        _state = replace(_state, recent_critical_errors=recent)


def record_worker_status(
    name: str,
    status: str,
    *,
    details: str | None = None,
    at: datetime | None = None,
) -> None:
    global _state
    updated_at = ensure_aware_utc(at or utcnow())
    record = WorkerStatusRecord(
        name=name.strip() or "worker",
        status=status.strip() or "unknown",
        details=details.strip() if isinstance(details, str) and details.strip() else None,
        updated_at=updated_at,
    )
    with _lock:
        remaining = tuple(item for item in _state.worker_statuses if item.name != record.name)
        _state = replace(_state, worker_statuses=(record, *remaining))


def record_backup_result(
    status: str,
    details: str,
    *,
    at: datetime | None = None,
) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            last_backup_result_at=ensure_aware_utc(at or utcnow()),
            last_backup_result_status=status.strip() or "unknown",
            last_backup_result_details=details.strip() or "unknown",
        )


def record_crypto_reconcile_run(
    *,
    processed_count: int,
    paid_count: int,
    expired_count: int,
    active_invoice_count: int,
    at: datetime | None = None,
) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            last_crypto_reconcile_at=ensure_aware_utc(at or utcnow()),
            last_crypto_reconcile_processed_count=processed_count,
            last_crypto_reconcile_paid_count=paid_count,
            last_crypto_reconcile_expired_count=expired_count,
            last_crypto_reconcile_active_invoice_count=active_invoice_count,
            last_crypto_reconcile_error_at=None,
            last_crypto_reconcile_error=None,
        )


def record_crypto_reconcile_error(message: str, *, at: datetime | None = None) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            last_crypto_reconcile_error_at=ensure_aware_utc(at or utcnow()),
            last_crypto_reconcile_error=message.strip(),
        )


def snapshot_runtime_state() -> RuntimeStateSnapshot:
    with _lock:
        return replace(_state)