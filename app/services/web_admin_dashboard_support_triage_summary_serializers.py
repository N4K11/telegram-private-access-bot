from __future__ import annotations

from app.services.web_admin_dashboard_support_triage_apply_summary_serializers import (
    _build_support_triage_apply_summary_views as _build_support_triage_apply_summary_views,
)
from app.services.web_admin_dashboard_support_triage_apply_summary_serializers import (
    _first_support_triage_item as _first_support_triage_item,
)
from app.services.web_admin_dashboard_support_triage_apply_summary_serializers import (
    _support_triage_summary_value as _support_triage_summary_value,
)


def _build_support_triage_summary_views(
    triage_views: dict[str, list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    top_triage_queue = _first_support_triage_item(triage_views["triage_queue"])
    top_triage_plan = _first_support_triage_item(triage_views["triage_plans"])
    top_triage_confirm = _first_support_triage_item(triage_views["triage_confirm"])
    return {
        "triage_queue_summary": {
            "top_triage_queue": _support_triage_summary_value(
                top_triage_queue,
                "key",
            ),
            "top_triage_queue_label": _support_triage_summary_value(
                top_triage_queue,
                "label",
            ),
            "top_pack_key": _support_triage_summary_value(
                top_triage_queue,
                "pack_key",
            ),
            "top_pack_label": _support_triage_summary_value(
                top_triage_queue,
                "pack_label",
            ),
            "top_route_label": _support_triage_summary_value(
                top_triage_queue,
                "route_label",
            ),
            "top_count": _support_triage_summary_value(
                top_triage_queue,
                "count",
                0,
            ),
            "top_share_percent": _support_triage_summary_value(
                top_triage_queue,
                "share_percent",
                0.0,
            ),
            "top_sample_ticket_ids": _support_triage_summary_value(
                top_triage_queue,
                "sample_ticket_ids",
                [],
            ),
            "top_hotspot": _support_triage_summary_value(
                top_triage_queue,
                "top_kind",
            ),
            "top_hotspot_label": _support_triage_summary_value(
                top_triage_queue,
                "top_kind_label",
            ),
            "top_priority": _support_triage_summary_value(
                top_triage_queue,
                "top_priority",
            ),
            "top_priority_label": _support_triage_summary_value(
                top_triage_queue,
                "top_priority_label",
            ),
            "top_note": _support_triage_summary_value(top_triage_queue, "note"),
        },
        "triage_plan_summary": {
            "top_triage_plan": _support_triage_summary_value(
                top_triage_plan,
                "key",
            ),
            "top_triage_plan_label": _support_triage_summary_value(
                top_triage_plan,
                "label",
            ),
            "top_route_key": _support_triage_summary_value(
                top_triage_plan,
                "route_key",
            ),
            "top_route_label": _support_triage_summary_value(
                top_triage_plan,
                "route_label",
            ),
            "top_primary_reply_key": _support_triage_summary_value(
                top_triage_plan,
                "primary_reply_key",
            ),
            "top_primary_reply_title": _support_triage_summary_value(
                top_triage_plan,
                "primary_reply_title",
            ),
            "top_count": _support_triage_summary_value(
                top_triage_plan,
                "count",
                0,
            ),
            "top_share_percent": _support_triage_summary_value(
                top_triage_plan,
                "share_percent",
                0.0,
            ),
            "top_sample_ticket_ids": _support_triage_summary_value(
                top_triage_plan,
                "sample_ticket_ids",
                [],
            ),
            "top_note": _support_triage_summary_value(top_triage_plan, "note"),
        },
        "triage_confirm_summary": {
            "top_triage_confirm": _support_triage_summary_value(
                top_triage_confirm,
                "confirm_key",
            ),
            "top_confirm_label": _support_triage_summary_value(
                top_triage_confirm,
                "confirm_label",
            ),
            "top_confirm_mode": _support_triage_summary_value(
                top_triage_confirm,
                "confirm_mode",
            ),
            "top_confirm_mode_label": _support_triage_summary_value(
                top_triage_confirm,
                "confirm_mode_label",
            ),
            "top_scope_label": _support_triage_summary_value(
                top_triage_confirm,
                "confirm_scope_label",
            ),
            "top_route_key": _support_triage_summary_value(
                top_triage_confirm,
                "route_key",
            ),
            "top_route_label": _support_triage_summary_value(
                top_triage_confirm,
                "route_label",
            ),
            "top_primary_reply_key": _support_triage_summary_value(
                top_triage_confirm,
                "primary_reply_key",
            ),
            "top_primary_reply_title": _support_triage_summary_value(
                top_triage_confirm,
                "primary_reply_title",
            ),
            "top_count": _support_triage_summary_value(
                top_triage_confirm,
                "count",
                0,
            ),
            "top_share_percent": _support_triage_summary_value(
                top_triage_confirm,
                "share_percent",
                0.0,
            ),
            "top_sample_ticket_ids": _support_triage_summary_value(
                top_triage_confirm,
                "sample_ticket_ids",
                [],
            ),
            "top_confirm_note": _support_triage_summary_value(
                top_triage_confirm,
                "confirm_note",
            ),
        },
        **_build_support_triage_apply_summary_views(triage_views),
    }
