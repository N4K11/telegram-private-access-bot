from __future__ import annotations

from app.services.admin_read_model_reporting_models import (
    AdminReadModelActionDigest,
    AdminReadModelActionItemSummary,
    AdminReadModelActionSummary,
    AdminReadModelDriftDigest,
    AdminReadModelDriftItemSummary,
    AdminReadModelDriftSummary,
    AdminReadModelFocusSummary,
    AdminReadModelOperatorDigest,
    AdminReadModelWatchItemSummary,
    AdminReadModelWatchlistDigest,
    AdminReadModelWatchlistSummary,
)
from app.services.admin_read_model_reporting_summaries import (
    _build_action_summary,
    _build_drift_summary,
    _build_watchlist_summary,
    _int_field,
    _item_field,
    _str_field,
)


def _build_action_item_detail(item: AdminReadModelActionItemSummary) -> str:
    detail = item.action_label or "check"
    if item.issue_summary_label:
        detail = f"{detail} · {item.issue_summary_label}"
    return detail


def _pick_drift_top_label(summary: AdminReadModelDriftSummary) -> str | None:
    return (
        summary.top_regression_label
        or summary.top_budget_regression_label
        or summary.top_query_regression_label
        or summary.top_payload_regression_label
        or summary.top_build_regression_label
    )


def _build_drift_item_detail(item: AdminReadModelDriftItemSummary) -> str:
    detail_parts: list[str] = []
    if item.budget_regressed:
        detail_parts.append("budget regression")
    if item.query_count_delta > 0:
        detail_parts.append(f"+{item.query_count_delta} queries")
    if item.payload_bytes_delta > 0:
        detail_parts.append(f"+{item.payload_bytes_delta} bytes")
    if item.build_duration_ms_delta > 0:
        detail_parts.append(f"+{item.build_duration_ms_delta} ms")
    return " · ".join(detail_parts) or (item.note or "drift detected")


def _build_watch_item_detail(item: AdminReadModelWatchItemSummary) -> str:
    detail_parts: list[str] = []
    if item.watch_kind_label:
        detail_parts.append(item.watch_kind_label)
    if item.source_mode_label:
        detail_parts.append(item.source_mode_label)
    return " · ".join(detail_parts) or (item.note or item.status_label or "watch item")


def build_admin_read_model_watchlist_digest(
    summary: AdminReadModelWatchlistSummary,
    *,
    max_items: int = 3,
) -> AdminReadModelWatchlistDigest:
    item_lines = tuple(
        f"{item.label}: {_build_watch_item_detail(item)}"
        for item in summary.top_items[:max(0, max_items)]
    )
    top_label = summary.top_attention_label or (
        summary.top_items[0].label if summary.top_items else None
    )
    top_detail = summary.top_attention_note
    if top_detail is None and top_label is not None:
        matching_item = next((item for item in summary.top_items if item.label == top_label), None)
        if matching_item is not None:
            top_detail = _build_watch_item_detail(matching_item)
        elif summary.top_attention_kind_label:
            top_detail = summary.top_attention_kind_label
    return AdminReadModelWatchlistDigest(
        summary_line=(
            f"alerts {summary.alert_item_count} · "
            f"missing {summary.missing_count} · "
            f"stale {summary.stale_count} · "
            f"budget {summary.budget_exceeded_count} · "
            f"drift {summary.regression_count}"
        ),
        top_label=top_label,
        top_detail=top_detail,
        item_lines=item_lines,
    )


def build_admin_read_model_action_digest(
    summary: AdminReadModelActionSummary,
    *,
    max_items: int = 3,
) -> AdminReadModelActionDigest:
    item_lines = tuple(
        f"{item.label}: {_build_action_item_detail(item)}"
        for item in summary.top_items[:max(0, max_items)]
    )
    top_label = summary.top_action_label or (
        summary.top_items[0].label if summary.top_items else None
    )
    top_detail = summary.top_action_note
    if top_detail is None and top_label is not None:
        matching_item = next((item for item in summary.top_items if item.label == top_label), None)
        if matching_item is not None:
            top_detail = _build_action_item_detail(matching_item)
    return AdminReadModelActionDigest(
        summary_line=(
            f"surfaces {summary.surface_count} · "
            f"snapshot {summary.snapshot_action_count} · "
            f"budget {summary.budget_action_count} · "
            f"drift {summary.drift_action_count}"
        ),
        top_label=top_label,
        top_detail=top_detail,
        item_lines=item_lines,
    )


def build_admin_read_model_drift_digest(
    summary: AdminReadModelDriftSummary,
    *,
    max_items: int = 3,
) -> AdminReadModelDriftDigest:
    item_lines = tuple(
        f"{item.label}: {_build_drift_item_detail(item)}"
        for item in summary.top_items[:max(0, max_items)]
    )
    top_label = _pick_drift_top_label(summary)
    top_detail = summary.top_regression_note
    if top_label is not None:
        matching_item = next((item for item in summary.top_items if item.label == top_label), None)
        if matching_item is not None:
            top_detail = _build_drift_item_detail(matching_item)
    return AdminReadModelDriftDigest(
        summary_line=(
            f"regressions {summary.regression_count} · "
            f"budget {summary.budget_regression_count} · "
            f"query {summary.query_regression_count} · "
            f"payload {summary.payload_regression_count}"
        ),
        extended_summary_line=(
            f"regressions {summary.regression_count} · "
            f"budget {summary.budget_regression_count} · "
            f"query {summary.query_regression_count} · "
            f"payload {summary.payload_regression_count} · "
            f"build {summary.build_regression_count} · "
            f"improvements {summary.improvement_count}"
        ),
        top_label=top_label,
        top_detail=top_detail,
        item_lines=item_lines,
    )


def build_admin_read_model_focus_summary(
    *,
    watchlist_summary: AdminReadModelWatchlistSummary | None = None,
    action_summary: AdminReadModelActionSummary | None = None,
    drift_summary: AdminReadModelDriftSummary | None = None,
) -> AdminReadModelFocusSummary | None:
    if drift_summary is not None and drift_summary.has_regressions:
        drift_digest = build_admin_read_model_drift_digest(drift_summary, max_items=1)
        if drift_digest.top_label:
            return AdminReadModelFocusSummary(
                kind="drift",
                kind_label="Live drift",
                label=drift_digest.top_label,
                detail=drift_digest.top_detail,
            )
    if watchlist_summary is not None and watchlist_summary.has_alerts:
        watchlist_digest = build_admin_read_model_watchlist_digest(
            watchlist_summary,
            max_items=1,
        )
        if watchlist_digest.top_label:
            return AdminReadModelFocusSummary(
                kind="watchlist",
                kind_label="Snapshot watch",
                label=watchlist_digest.top_label,
                detail=watchlist_digest.top_detail,
            )
    if action_summary is not None and action_summary.has_actions:
        action_digest = build_admin_read_model_action_digest(action_summary, max_items=1)
        if action_digest.top_label:
            return AdminReadModelFocusSummary(
                kind="action",
                kind_label="Next action",
                label=action_digest.top_label,
                detail=action_digest.top_detail,
            )
    return None


def build_admin_read_model_operator_digest(
    *,
    watchlist_summary: AdminReadModelWatchlistSummary | None = None,
    action_summary: AdminReadModelActionSummary | None = None,
    drift_summary: AdminReadModelDriftSummary | None = None,
) -> AdminReadModelOperatorDigest | None:
    focus_summary = build_admin_read_model_focus_summary(
        watchlist_summary=watchlist_summary,
        action_summary=action_summary,
        drift_summary=drift_summary,
    )
    watch_digest = (
        build_admin_read_model_watchlist_digest(watchlist_summary, max_items=1)
        if watchlist_summary is not None
        else None
    )
    action_digest = (
        build_admin_read_model_action_digest(action_summary, max_items=1)
        if action_summary is not None
        else None
    )
    drift_digest = (
        build_admin_read_model_drift_digest(drift_summary, max_items=1)
        if drift_summary is not None and drift_summary.has_regressions
        else None
    )

    summary_parts: list[str] = []
    if focus_summary is not None:
        summary_parts.append(f"focus {focus_summary.kind_label.lower()}: {focus_summary.label}")
    if watch_digest is not None:
        summary_parts.append(f"watch {watch_digest.summary_line}")
    if action_digest is not None:
        summary_parts.append(f"actions {action_digest.summary_line}")
    if drift_summary is not None:
        if drift_digest is not None:
            summary_parts.append(f"drift {drift_digest.summary_line}")
        else:
            summary_parts.append("drift ok")

    if not summary_parts:
        return None

    watch_line = None
    if watch_digest is not None and watch_digest.top_label:
        watch_line = (
            f"{watch_digest.top_label} В· "
            f"{watch_digest.top_detail or 'watch item'}"
        )
    action_line = None
    if action_digest is not None and action_digest.top_label:
        action_line = (
            f"{action_digest.top_label} В· "
            f"{action_digest.top_detail or 'action item'}"
        )
    drift_line = None
    if drift_digest is not None and drift_digest.top_label:
        drift_line = (
            f"{drift_digest.top_label} В· "
            f"{drift_digest.top_detail or 'drift detected'}"
        )

    return AdminReadModelOperatorDigest(
        summary_line=" В· ".join(summary_parts),
        focus_line=focus_summary.line if focus_summary is not None else None,
        watch_line=watch_line,
        action_line=action_line,
        drift_line=drift_line,
    )


def build_admin_read_model_operator_digest_payload(
    *,
    watchlist_payload: dict[str, object] | None = None,
    action_payload: dict[str, object] | None = None,
    drift_payload: dict[str, object] | None = None,
) -> dict[str, str] | None:
    watchlist_summary = (
        _build_watchlist_summary(watchlist_payload)
        if isinstance(watchlist_payload, dict)
        else None
    )
    action_summary = (
        _build_action_summary(action_payload)
        if isinstance(action_payload, dict)
        else None
    )
    drift_summary = (
        _build_drift_summary(drift_payload)
        if isinstance(drift_payload, dict)
        else None
    )
    operator_digest = build_admin_read_model_operator_digest(
        watchlist_summary=watchlist_summary,
        action_summary=action_summary,
        drift_summary=drift_summary,
    )
    if operator_digest is None:
        return None
    return {
        "summary_line": operator_digest.summary_line,
        "focus_line": operator_digest.focus_line or "",
        "watch_line": operator_digest.watch_line or "",
        "action_line": operator_digest.action_line or "",
        "drift_line": operator_digest.drift_line or "",
    }


def build_admin_read_model_focus_payload(
    *,
    watchlist_payload: dict[str, object] | None = None,
    action_payload: dict[str, object] | None = None,
    drift_payload: dict[str, object] | None = None,
) -> dict[str, str] | None:
    watchlist_summary = (
        _build_watchlist_summary(watchlist_payload)
        if isinstance(watchlist_payload, dict)
        else None
    )
    action_summary = (
        _build_action_summary(action_payload)
        if isinstance(action_payload, dict)
        else None
    )
    drift_summary = (
        _build_drift_summary(drift_payload)
        if isinstance(drift_payload, dict)
        else None
    )
    focus_summary = build_admin_read_model_focus_summary(
        watchlist_summary=watchlist_summary,
        action_summary=action_summary,
        drift_summary=drift_summary,
    )
    if focus_summary is None:
        return None
    return {
        "kind": focus_summary.kind,
        "kind_label": focus_summary.kind_label,
        "label": focus_summary.label,
        "detail": focus_summary.detail or "",
        "line": focus_summary.line,
    }


def build_admin_read_model_snapshot_focus_payload(
    overview_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(overview_payload, dict):
        return None
    existing_focus = overview_payload.get("focus_summary")
    if isinstance(existing_focus, dict):
        line = _str_field(existing_focus, "line")
        kind = _str_field(existing_focus, "kind")
        kind_label = _str_field(existing_focus, "kind_label")
        label = _str_field(existing_focus, "label")
        if line and kind and kind_label and label:
            alert_item_count = _int_field(overview_payload, "alert_item_count")
            if alert_item_count <= 0:
                alert_item_count = (
                    _int_field(overview_payload, "missing_count")
                    + _int_field(overview_payload, "stale_count")
                    + _int_field(overview_payload, "budget_exceeded_count")
                )
            return {
                "kind": kind,
                "kind_label": kind_label,
                "label": label,
                "detail": _str_field(existing_focus, "detail") or "",
                "line": line,
                "source": str(overview_payload.get("source") or "snapshot"),
                "generated_at_label": _str_field(overview_payload, "generated_at_label") or "",
                "staleness_seconds": _int_field(overview_payload, "staleness_seconds"),
                "tracked_count": _int_field(overview_payload, "tracked_count"),
                "alert_item_count": alert_item_count,
                "missing_count": _int_field(overview_payload, "missing_count"),
                "stale_count": _int_field(overview_payload, "stale_count"),
                "budget_exceeded_count": _int_field(overview_payload, "budget_exceeded_count"),
            }
    watchlist_summary = AdminReadModelWatchlistSummary(
        source=str(overview_payload.get("source") or "snapshot"),
        generated_at_label=_str_field(overview_payload, "generated_at_label"),
        staleness_seconds=_int_field(overview_payload, "staleness_seconds"),
        tracked_count=_int_field(overview_payload, "tracked_count"),
        alert_item_count=(
            _int_field(overview_payload, "alert_item_count")
            or _int_field(overview_payload, "missing_count")
            + _int_field(overview_payload, "stale_count")
            + _int_field(overview_payload, "budget_exceeded_count")
        ),
        missing_count=_int_field(overview_payload, "missing_count"),
        stale_count=_int_field(overview_payload, "stale_count"),
        budget_exceeded_count=_int_field(overview_payload, "budget_exceeded_count"),
        regression_count=0,
        top_attention_label=_item_field(overview_payload, "top_attention_item", "label"),
        top_attention_kind_label=_item_field(
            overview_payload,
            "top_attention_item",
            "status_label",
        ),
        top_attention_note=_item_field(overview_payload, "top_attention_item", "note"),
        top_regression_label=None,
        top_budget_label=None,
        top_items=(),
    )
    focus_summary = build_admin_read_model_focus_summary(
        watchlist_summary=watchlist_summary,
    )
    if focus_summary is None:
        return None
    return {
        "kind": focus_summary.kind,
        "kind_label": focus_summary.kind_label,
        "label": focus_summary.label,
        "detail": focus_summary.detail or "",
        "line": focus_summary.line,
        "source": watchlist_summary.source,
        "generated_at_label": watchlist_summary.generated_at_label or "",
        "staleness_seconds": watchlist_summary.staleness_seconds,
        "tracked_count": watchlist_summary.tracked_count,
        "alert_item_count": watchlist_summary.alert_item_count,
        "missing_count": watchlist_summary.missing_count,
        "stale_count": watchlist_summary.stale_count,
        "budget_exceeded_count": watchlist_summary.budget_exceeded_count,
    }


def build_admin_read_model_snapshot_digest_payload(
    overview_payload: dict[str, object] | None,
    *,
    watchlist_payload: dict[str, object] | None = None,
    action_payload: dict[str, object] | None = None,
) -> dict[str, object] | None:
    if not isinstance(overview_payload, dict):
        return None
    existing_digest = overview_payload.get("digest_summary")
    if isinstance(existing_digest, dict):
        watch_summary_line = _str_field(existing_digest, "watch_summary_line")
        action_summary_line = _str_field(existing_digest, "action_summary_line")
        if watch_summary_line and action_summary_line:
            return {
                "tracked_count": _int_field(existing_digest, "tracked_count"),
                "alert_item_count": _int_field(existing_digest, "alert_item_count"),
                "missing_count": _int_field(existing_digest, "missing_count"),
                "stale_count": _int_field(existing_digest, "stale_count"),
                "budget_exceeded_count": _int_field(existing_digest, "budget_exceeded_count"),
                "watch_summary_line": watch_summary_line,
                "action_summary_line": action_summary_line,
                "top_watch_label": _str_field(existing_digest, "top_watch_label") or "",
                "top_watch_detail": _str_field(existing_digest, "top_watch_detail") or "",
                "top_action_label": _str_field(existing_digest, "top_action_label") or "",
                "top_action_detail": _str_field(existing_digest, "top_action_detail") or "",
                "generated_at_label": _str_field(existing_digest, "generated_at_label") or "",
                "staleness_seconds": _int_field(existing_digest, "staleness_seconds"),
            }
    if not isinstance(watchlist_payload, dict):
        watchlist_payload = overview_payload
    watchlist_summary = _build_watchlist_summary(watchlist_payload)
    action_summary = (
        _build_action_summary(action_payload)
        if isinstance(action_payload, dict)
        else None
    )
    if action_summary is None:
        return None
    watch_digest = build_admin_read_model_watchlist_digest(watchlist_summary, max_items=1)
    action_digest = build_admin_read_model_action_digest(action_summary, max_items=1)
    return {
        "tracked_count": watchlist_summary.tracked_count,
        "alert_item_count": watchlist_summary.alert_item_count,
        "missing_count": watchlist_summary.missing_count,
        "stale_count": watchlist_summary.stale_count,
        "budget_exceeded_count": watchlist_summary.budget_exceeded_count,
        "watch_summary_line": watch_digest.summary_line,
        "action_summary_line": action_digest.summary_line,
        "top_watch_label": watch_digest.top_label or "",
        "top_watch_detail": watch_digest.top_detail or "",
        "top_action_label": action_digest.top_label or "",
        "top_action_detail": action_digest.top_detail or "",
        "generated_at_label": watchlist_summary.generated_at_label or "",
        "staleness_seconds": watchlist_summary.staleness_seconds,
    }


def build_admin_read_model_snapshot_operator_payload(
    overview_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(overview_payload, dict):
        return None
    focus_payload = build_admin_read_model_snapshot_focus_payload(overview_payload)
    digest_payload = build_admin_read_model_snapshot_digest_payload(overview_payload)
    existing_operator = overview_payload.get("operator_digest_summary")

    summary_line = None
    focus_line = ""
    watch_line = ""
    action_line = ""
    drift_line = ""

    if isinstance(existing_operator, dict):
        summary_line = _str_field(existing_operator, "summary_line")
        focus_line = _str_field(existing_operator, "focus_line") or ""
        watch_line = _str_field(existing_operator, "watch_line") or ""
        action_line = _str_field(existing_operator, "action_line") or ""
        drift_line = _str_field(existing_operator, "drift_line") or ""

    if not focus_line and isinstance(focus_payload, dict):
        focus_line = _str_field(focus_payload, "line") or ""
    if not watch_line and isinstance(digest_payload, dict):
        top_watch_label = _str_field(digest_payload, "top_watch_label") or ""
        top_watch_detail = _str_field(digest_payload, "top_watch_detail") or ""
        if top_watch_label:
            watch_line = (
                f"{top_watch_label} В· {top_watch_detail}"
                if top_watch_detail
                else top_watch_label
            )
    if not action_line and isinstance(digest_payload, dict):
        top_action_label = _str_field(digest_payload, "top_action_label") or ""
        top_action_detail = _str_field(digest_payload, "top_action_detail") or ""
        if top_action_label:
            action_line = (
                f"{top_action_label} В· {top_action_detail}"
                if top_action_detail
                else top_action_label
            )

    if summary_line is None:
        summary_parts: list[str] = []
        if focus_line:
            summary_parts.append(focus_line)
        if isinstance(digest_payload, dict):
            watch_summary_line = _str_field(digest_payload, "watch_summary_line")
            action_summary_line = _str_field(digest_payload, "action_summary_line")
            if watch_summary_line:
                summary_parts.append(f"watch {watch_summary_line}")
            if action_summary_line:
                summary_parts.append(f"actions {action_summary_line}")
        summary_line = " В· ".join(summary_parts) if summary_parts else None

    if not summary_line:
        return None

    tracked_count = 0
    alert_item_count = 0
    missing_count = 0
    stale_count = 0
    budget_exceeded_count = 0
    generated_at_label = ""
    staleness_seconds = 0
    if isinstance(digest_payload, dict):
        tracked_count = _int_field(digest_payload, "tracked_count")
        alert_item_count = _int_field(digest_payload, "alert_item_count")
        missing_count = _int_field(digest_payload, "missing_count")
        stale_count = _int_field(digest_payload, "stale_count")
        budget_exceeded_count = _int_field(digest_payload, "budget_exceeded_count")
        generated_at_label = _str_field(digest_payload, "generated_at_label") or ""
        staleness_seconds = _int_field(digest_payload, "staleness_seconds")
    elif isinstance(focus_payload, dict):
        tracked_count = _int_field(focus_payload, "tracked_count")
        alert_item_count = _int_field(focus_payload, "alert_item_count")
        missing_count = _int_field(focus_payload, "missing_count")
        stale_count = _int_field(focus_payload, "stale_count")
        budget_exceeded_count = _int_field(focus_payload, "budget_exceeded_count")
        generated_at_label = _str_field(focus_payload, "generated_at_label") or ""
        staleness_seconds = _int_field(focus_payload, "staleness_seconds")

    return {
        "summary_line": summary_line,
        "focus_line": focus_line,
        "watch_line": watch_line,
        "action_line": action_line,
        "drift_line": drift_line,
        "tracked_count": tracked_count,
        "alert_item_count": alert_item_count,
        "missing_count": missing_count,
        "stale_count": stale_count,
        "budget_exceeded_count": budget_exceeded_count,
        "generated_at_label": generated_at_label,
        "staleness_seconds": staleness_seconds,
    }
