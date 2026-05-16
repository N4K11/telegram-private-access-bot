from __future__ import annotations

from typing import Any

READ_MODEL_TEXT_TITLE = "🗂 Read-model diagnostics"
READ_MODEL_DRIFT_TITLE = "🧪 Snapshot vs live drift"
READ_MODEL_WATCHLIST_TITLE = "⚠️ Read-model watchlist"
READ_MODEL_ACTIONS_TITLE = "🛠 Read-model action digest"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_str(value: Any, default: str = "—") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _status_icon(status: str) -> str:
    return {
        "ok": "✅",
        "stable": "✅",
        "improved": "✅",
        "budget": "⚠️",
        "stale": "⚠️",
        "regression": "⚠️",
        "missing": "❌",
    }.get(str(status).strip().lower(), "ℹ️")


def _render_meta(payload: dict[str, object]) -> list[str]:
    lines = [
        f"Source: {_as_str(payload.get('source'))}",
        f"Generated: {_as_str(payload.get('generated_at_label'))}",
        f"Build: {_as_int(payload.get('build_duration_ms'))} ms",
    ]
    query_budget = payload.get("query_budget")
    if query_budget is not None:
        lines.append(
            "Queries: "
            f"{_as_int(payload.get('query_count'))}/{_as_int(query_budget)}"
        )
    payload_budget = payload.get("payload_budget")
    if payload_budget is not None:
        lines.append(
            "Payload: "
            f"{_as_int(payload.get('payload_bytes'))}/{_as_int(payload_budget)} bytes"
        )
    return lines


def _render_focus(payload: dict[str, object]) -> str | None:
    focus_summary = payload.get("focus_summary")
    if not isinstance(focus_summary, dict):
        return None
    line = _as_str(focus_summary.get("line"), default="")
    if not line:
        return None
    return f"Focus: {line}"


def _render_operator_summary(payload: dict[str, object]) -> str | None:
    operator_digest = payload.get("operator_digest_summary")
    if not isinstance(operator_digest, dict):
        return None
    summary_line = _as_str(operator_digest.get("summary_line"), default="")
    if not summary_line:
        return None
    return f"Summary: {summary_line}"


def _render_overview(payload: dict[str, object]) -> str:
    top_attention = payload.get("top_attention_item")
    top_query = payload.get("top_query_item")
    top_payload = payload.get("top_payload_item")
    top_build = payload.get("top_build_item")
    items = payload.get("items")
    lines = [READ_MODEL_TEXT_TITLE, ""]
    lines.extend(_render_meta(payload))
    summary_line = _render_operator_summary(payload)
    if summary_line:
        lines.append(summary_line)
    focus_line = _render_focus(payload)
    if focus_line:
        lines.append(focus_line)
    lines.append("")
    lines.append(
        "Tracked: "
        f"{_as_int(payload.get('available_count'))}/"
        f"{_as_int(payload.get('tracked_count'))} available"
    )
    lines.append(
        "Alerts: "
        f"missing {_as_int(payload.get('missing_count'))} · "
        f"stale {_as_int(payload.get('stale_count'))} · "
        f"budget {_as_int(payload.get('budget_exceeded_count'))}"
    )
    if isinstance(top_attention, dict):
        lines.append(
            "Top risk: "
            f"{_as_str(top_attention.get('label'))} · {_as_str(top_attention.get('status_label'))}"
        )
    if isinstance(top_query, dict):
        lines.append(
            "Top query cost: "
            f"{_as_str(top_query.get('label'))} · {_as_int(top_query.get('query_count'))}"
        )
    if isinstance(top_payload, dict):
        lines.append(
            "Top payload: "
            f"{_as_str(top_payload.get('label'))} · "
            f"{_as_int(top_payload.get('payload_bytes'))} bytes"
        )
    if isinstance(top_build, dict):
        lines.append(
            "Top build: "
            f"{_as_str(top_build.get('label'))} · {_as_int(top_build.get('build_duration_ms'))} ms"
        )

    if isinstance(items, list) and items:
        lines.append("")
        lines.append("Items:")
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"{_status_icon(_as_str(item.get('status')))} "
                f"{_as_str(item.get('label'))}: {_as_str(item.get('status_label'))}"
            )
            lines.append(
                "  "
                f"age {_as_int(item.get('staleness_seconds'))}s · "
                f"queries {_as_int(item.get('query_count'))}/{_as_int(item.get('query_budget'))} · "
                f"bytes {_as_int(item.get('payload_bytes'))}/"
                f"{_as_int(item.get('payload_budget'))} · "
                f"build {_as_int(item.get('build_duration_ms'))} ms"
            )
    return "\n".join(lines)


def _render_drift(payload: dict[str, object]) -> str:
    top_regression = payload.get("top_regression_item")
    top_budget = payload.get("top_budget_regression_item")
    top_improvement = payload.get("top_improvement_item")
    items = payload.get("items")
    lines = [READ_MODEL_DRIFT_TITLE, ""]
    lines.extend(_render_meta(payload))
    summary_line = _render_operator_summary(payload)
    if summary_line:
        lines.append(summary_line)
    focus_line = _render_focus(payload)
    if focus_line:
        lines.append(focus_line)
    lines.append("")
    lines.append(
        "Compared: "
        f"{_as_int(payload.get('compared_count'))}/{_as_int(payload.get('tracked_count'))}"
    )
    lines.append(
        "Drift: "
        f"regressions {_as_int(payload.get('regression_count'))} · "
        f"budget {_as_int(payload.get('budget_regression_count'))} · "
        f"improvements {_as_int(payload.get('improvement_count'))} · "
        f"missing {_as_int(payload.get('missing_snapshot_count'))}"
    )
    if isinstance(top_regression, dict):
        lines.append(
            "Top regression: "
            f"{_as_str(top_regression.get('label'))} · {_as_str(top_regression.get('note'))}"
        )
    if isinstance(top_budget, dict):
        lines.append(
            "Top budget regression: "
            f"{_as_str(top_budget.get('label'))}"
        )
    if isinstance(top_improvement, dict):
        lines.append(
            "Top improvement: "
            f"{_as_str(top_improvement.get('label'))}"
        )

    if isinstance(items, list) and items:
        lines.append("")
        lines.append("Items:")
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"{_status_icon(_as_str(item.get('status')))} "
                f"{_as_str(item.get('label'))}: {_as_str(item.get('status_label'))}"
            )
            lines.append(
                "  "
                f"Δq {_as_int(item.get('query_count_delta'))} · "
                f"Δbytes {_as_int(item.get('payload_bytes_delta'))} · "
                f"Δms {_as_int(item.get('build_duration_ms_delta'))}"
            )
    return "\n".join(lines)


def _render_watchlist(payload: dict[str, object]) -> str:
    top_attention = payload.get("top_attention_item")
    top_regression = payload.get("top_regression_item")
    top_budget = payload.get("top_budget_item")
    items = payload.get("items")
    lines = [READ_MODEL_WATCHLIST_TITLE, ""]
    lines.extend(_render_meta(payload))
    summary_line = _render_operator_summary(payload)
    if summary_line:
        lines.append(summary_line)
    focus_line = _render_focus(payload)
    if focus_line:
        lines.append(focus_line)
    lines.append("")
    lines.append(
        "Open alerts: "
        f"{_as_int(payload.get('alert_item_count'))} of {_as_int(payload.get('tracked_count'))}"
    )
    lines.append(
        "Kinds: "
        f"missing {_as_int(payload.get('missing_count'))} · "
        f"stale {_as_int(payload.get('stale_count'))} · "
        f"budget {_as_int(payload.get('budget_exceeded_count'))} · "
        f"drift {_as_int(payload.get('regression_count'))}"
    )
    if isinstance(top_attention, dict):
        lines.append(
            "Top attention: "
            f"{_as_str(top_attention.get('label'))} · "
            f"{_as_str(top_attention.get('watch_kind_label'))}"
        )
    if isinstance(top_regression, dict):
        lines.append(
            "Top drift: "
            f"{_as_str(top_regression.get('label'))}"
        )
    if isinstance(top_budget, dict):
        lines.append(
            "Top budget issue: "
            f"{_as_str(top_budget.get('label'))}"
        )
    if isinstance(items, list) and items:
        lines.append("")
        lines.append("Items:")
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"{_status_icon(_as_str(item.get('status')))} "
                f"{_as_str(item.get('label'))}: {_as_str(item.get('watch_kind_label'))}"
            )
            lines.append(
                "  "
                f"{_as_str(item.get('source_mode_label'))} · "
                f"queries {_as_int(item.get('query_count'))}/{_as_int(item.get('query_budget'))} · "
                f"bytes {_as_int(item.get('payload_bytes'))}/{_as_int(item.get('payload_budget'))}"
            )
    return "\n".join(lines)


def _render_actions(payload: dict[str, object]) -> str:
    top_action = payload.get("top_action_item")
    top_snapshot = payload.get("top_snapshot_action_item")
    top_budget = payload.get("top_budget_action_item")
    top_drift = payload.get("top_drift_action_item")
    items = payload.get("items")
    lines = [READ_MODEL_ACTIONS_TITLE, ""]
    lines.extend(_render_meta(payload))
    summary_line = _render_operator_summary(payload)
    if summary_line:
        lines.append(summary_line)
    focus_line = _render_focus(payload)
    if focus_line:
        lines.append(focus_line)
    lines.append("")
    lines.append(
        "Surfaces: "
        f"{_as_int(payload.get('surface_count'))} of {_as_int(payload.get('tracked_count'))}"
    )
    lines.append(
        "Action mix: "
        f"snapshot {_as_int(payload.get('snapshot_action_count'))} · "
        f"budget {_as_int(payload.get('budget_action_count'))} · "
        f"drift {_as_int(payload.get('drift_action_count'))}"
    )
    if isinstance(top_action, dict):
        lines.append(
            "Top action: "
            f"{_as_str(top_action.get('label'))} · {_as_str(top_action.get('action_label'))}"
        )
    if isinstance(top_snapshot, dict):
        lines.append(
            "Top snapshot action: "
            f"{_as_str(top_snapshot.get('label'))}"
        )
    if isinstance(top_budget, dict):
        lines.append(
            "Top budget action: "
            f"{_as_str(top_budget.get('label'))}"
        )
    if isinstance(top_drift, dict):
        lines.append(
            "Top drift action: "
            f"{_as_str(top_drift.get('label'))}"
        )
    if isinstance(items, list) and items:
        lines.append("")
        lines.append("Items:")
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"{_status_icon(_as_str(item.get('status')))} "
                f"{_as_str(item.get('label'))}: {_as_str(item.get('action_label'))}"
            )
            lines.append(
                "  "
                f"{_as_str(item.get('action_category_label'))} · "
                f"{_as_str(item.get('issue_summary_label'))}"
            )
            lines.append(
                "  "
                f"{_as_str(item.get('source_mode_label'))} · "
                f"queries {_as_int(item.get('query_count'))}/{_as_int(item.get('query_budget'))} · "
                f"bytes {_as_int(item.get('payload_bytes'))}/{_as_int(item.get('payload_budget'))}"
            )
            lines.append(f"  {_as_str(item.get('action_note'))}")
    return "\n".join(lines)


def render_admin_read_models_text(payload: dict[str, object]) -> str:
    view = _as_str(payload.get("view"), "overview").lower()
    if view == "drift":
        return _render_drift(payload)
    if view == "watchlist":
        return _render_watchlist(payload)
    if view == "actions":
        return _render_actions(payload)
    return _render_overview(payload)
