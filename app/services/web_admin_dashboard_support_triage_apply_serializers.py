# ruff: noqa: E501
from __future__ import annotations

from app.services.web_admin_dashboard_support_triage_apply_view_serializers import (
    _build_support_triage_apply_views as _build_support_triage_apply_views,
)
from app.services.web_admin_dashboard_support_triage_apply_view_serializers import (
    _support_triage_apply_effectiveness_coverage_label as _support_triage_apply_effectiveness_coverage_label,
)
from app.services.web_admin_dashboard_support_triage_queue_serializers import (
    _build_support_triage_confirm as _build_support_triage_confirm,
)
from app.services.web_admin_dashboard_support_triage_queue_serializers import (
    _build_support_triage_plans as _build_support_triage_plans,
)
from app.services.web_admin_dashboard_support_triage_queue_serializers import (
    _build_support_triage_queue as _build_support_triage_queue,
)
from app.services.web_admin_dashboard_support_triage_queue_serializers import (
    _support_triage_confirm_label as _support_triage_confirm_label,
)
from app.services.web_admin_dashboard_support_triage_queue_serializers import (
    _support_triage_confirm_note as _support_triage_confirm_note,
)
from app.services.web_admin_dashboard_support_triage_queue_serializers import (
    _support_triage_confirm_scope_label as _support_triage_confirm_scope_label,
)
from app.services.web_admin_dashboard_support_triage_summary_serializers import (
    _build_support_triage_summary_views as _build_support_triage_summary_views,
)
from app.services.web_admin_dashboard_support_triage_summary_serializers import (
    _first_support_triage_item as _first_support_triage_item,
)
from app.services.web_admin_dashboard_support_triage_summary_serializers import (
    _support_triage_summary_value as _support_triage_summary_value,
)


def _build_support_triage_views(
    insights,
    *,
    open_total: int,
) -> dict[str, list[dict[str, object]]]:
    triage_queue = _build_support_triage_queue(insights, open_total=open_total)
    triage_plans = _build_support_triage_plans(triage_queue)
    triage_confirm = _build_support_triage_confirm(triage_plans)
    return {
        "triage_queue": triage_queue,
        "triage_plans": triage_plans,
        "triage_confirm": triage_confirm,
        **_build_support_triage_apply_views(insights),
    }
