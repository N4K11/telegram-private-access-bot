from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_BUDGET as READ_MODEL_STATUS_BUDGET,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_IMPROVED as READ_MODEL_STATUS_IMPROVED,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_MISSING as READ_MODEL_STATUS_MISSING,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_OK as READ_MODEL_STATUS_OK,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_REGRESSION as READ_MODEL_STATUS_REGRESSION,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_STATUS_STALE as READ_MODEL_STATUS_STALE,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_VIEW_ACTIONS as READ_MODEL_VIEW_ACTIONS,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_VIEW_DRIFT as READ_MODEL_VIEW_DRIFT,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_VIEW_LABELS as READ_MODEL_VIEW_LABELS,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_VIEW_OVERVIEW as READ_MODEL_VIEW_OVERVIEW,
)
from app.services.web_admin_dashboard_read_model_core import (
    READ_MODEL_VIEW_WATCHLIST as READ_MODEL_VIEW_WATCHLIST,
)
from app.services.web_admin_dashboard_read_model_core import (
    _bool_or_none as _bool_or_none,
)
from app.services.web_admin_dashboard_read_model_core import (
    _decode_payload as _decode_payload,
)
from app.services.web_admin_dashboard_read_model_core import (
    _int_or_default as _int_or_default,
)
from app.services.web_admin_dashboard_read_model_core import (
    _model_scope_label as _model_scope_label,
)
from app.services.web_admin_dashboard_read_model_core import (
    _read_model_note as _read_model_note,
)
from app.services.web_admin_dashboard_read_model_core import (
    _read_model_severity as _read_model_severity,
)
from app.services.web_admin_dashboard_read_model_core import (
    _read_model_status as _read_model_status,
)
from app.services.web_admin_dashboard_read_model_core import (
    _staleness_seconds as _staleness_seconds,
)
from app.services.web_admin_dashboard_read_model_descriptors import ReadModelDescriptor
from app.services.web_admin_dashboard_read_model_drift_serializers import (
    _build_drift_item as _build_drift_item,
)
from app.services.web_admin_dashboard_read_model_drift_serializers import (
    _drift_tone as _drift_tone,
)
from app.utils.datetime import ensure_aware_utc, format_datetime


def _build_model_item(
    descriptor: ReadModelDescriptor,
    *,
    payload: dict[str, object] | None,
    generated_at: datetime | None,
    now: datetime,
    settings: Settings,
) -> dict[str, object]:
    is_missing = payload is None or generated_at is None
    query_count = None if payload is None else _int_or_default(payload.get("query_count"))
    query_budget = (
        descriptor.query_budget
        if payload is None
        else _int_or_default(payload.get("query_budget"), descriptor.query_budget or 0)
    )
    if (
        descriptor.query_budget is None
        and payload is not None
        and payload.get("query_budget") is None
    ):
        query_budget = None
    query_budget_ok = None if payload is None else _bool_or_none(payload.get("query_budget_ok"))
    if query_budget_ok is None and query_budget is not None and query_count is not None:
        query_budget_ok = query_count <= query_budget
    payload_bytes = None if payload is None else _int_or_default(payload.get("payload_bytes"))
    payload_budget = (
        descriptor.payload_budget
        if payload is None
        else _int_or_default(payload.get("payload_budget"), descriptor.payload_budget or 0)
    )
    if (
        descriptor.payload_budget is None
        and payload is not None
        and payload.get("payload_budget") is None
    ):
        payload_budget = None
    payload_budget_ok = None if payload is None else _bool_or_none(payload.get("payload_budget_ok"))
    if payload_budget_ok is None and payload_budget is not None and payload_bytes is not None:
        payload_budget_ok = payload_bytes <= payload_budget
    build_duration_ms = None if payload is None else _int_or_default(
        payload.get("build_duration_ms")
    )
    payload_source = "missing" if payload is None else str(payload.get("source") or "unknown")
    staleness_seconds = _staleness_seconds(generated_at=generated_at, now=now)
    is_stale = is_missing or (staleness_seconds or 0) > (descriptor.cadence_minutes * 60)
    status, status_label = _read_model_status(
        is_missing=is_missing,
        is_stale=is_stale,
        query_budget_ok=query_budget_ok,
    )
    return {
        "id": descriptor.identity,
        "group": descriptor.storage_group,
        "group_label": descriptor.storage_group.title(),
        "key": descriptor.storage_key,
        "scope_key": descriptor.scope_key,
        "scope_label": _model_scope_label(descriptor),
        "label": descriptor.label,
        "payload_source": payload_source,
        "generated_at": ensure_aware_utc(generated_at).isoformat() if generated_at else None,
        "generated_at_label": (
            format_datetime(generated_at, settings.timezone)
            if generated_at is not None
            else "Missing"
        ),
        "staleness_seconds": staleness_seconds,
        "cadence_minutes": descriptor.cadence_minutes,
        "query_count": query_count,
        "query_budget": query_budget,
        "query_budget_ok": query_budget_ok,
        "payload_bytes": payload_bytes,
        "payload_budget": payload_budget,
        "payload_budget_ok": payload_budget_ok,
        "build_duration_ms": build_duration_ms,
        "is_missing": is_missing,
        "is_stale": is_stale,
        "status": status,
        "status_label": status_label,
        "note": _read_model_note(
            is_missing=is_missing,
            is_stale=is_stale,
            descriptor=descriptor,
            query_budget_ok=query_budget_ok,
            query_count=query_count,
            query_budget=query_budget,
            payload_budget_ok=payload_budget_ok,
            payload_bytes=payload_bytes,
            payload_budget=payload_budget,
        ),
        "severity_score": _read_model_severity(
            is_missing=is_missing,
            is_stale=is_stale,
            query_budget_ok=query_budget_ok,
            payload_budget_ok=payload_budget_ok,
            staleness_seconds=staleness_seconds,
            query_count=query_count,
            payload_bytes=payload_bytes,
            build_duration_ms=build_duration_ms,
        ),
    }


def _leader_item(
    items: list[dict[str, object]],
    *,
    field: str,
) -> dict[str, object] | None:
    available = [item for item in items if not item["is_missing"] and item.get(field) is not None]
    if not available:
        return None
    return max(available, key=lambda item: _int_or_default(item.get(field)))


def _sort_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (
            _int_or_default(item.get("severity_score")),
            _int_or_default(item.get("staleness_seconds")),
            _int_or_default(item.get("query_count")),
            _int_or_default(item.get("payload_bytes")),
            _int_or_default(item.get("build_duration_ms")),
        ),
        reverse=True,
    )


def _normalize_read_model_view(raw_value: str | None) -> str:
    normalized = str(raw_value or READ_MODEL_VIEW_OVERVIEW).strip().lower()
    if normalized not in READ_MODEL_VIEW_LABELS:
        return READ_MODEL_VIEW_OVERVIEW
    return normalized


def _available_read_model_views() -> list[dict[str, str]]:
    return [
        {"key": key, "label": label}
        for key, label in READ_MODEL_VIEW_LABELS.items()
    ]

