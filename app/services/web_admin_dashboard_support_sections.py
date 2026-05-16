from __future__ import annotations

from app.services import (
    web_admin_dashboard_support_inbox_sections as support_inbox_sections,
)
from app.services import (
    web_admin_dashboard_support_insight_sections as support_insight_sections,
)
from app.services import (
    web_admin_dashboard_support_ticket_sections as support_ticket_sections,
)
from app.services.web_admin_dashboard_support_actions import (
    run_web_admin_support_triage_apply_action as run_web_admin_support_triage_apply_action,
)
from app.services.web_admin_dashboard_support_actions import (
    run_web_admin_support_triage_confirm_action as run_web_admin_support_triage_confirm_action,
)
from app.services.web_admin_dashboard_support_insight_serializers import (
    _serialize_support_insights as _serialize_support_insights,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _matches_support_queue as _matches_support_queue,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _paginate as _paginate,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _serialize_support_close_reason_analytics as _serialize_support_close_reason_analytics,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _serialize_support_ticket_list_item as _serialize_support_ticket_list_item,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _support_queue_counts as _support_queue_counts,
)
from app.services.web_admin_dashboard_support_ticket_serializers import (
    _support_search_blob as _support_search_blob,
)

DEFAULT_PAGE_SIZE = support_inbox_sections.DEFAULT_PAGE_SIZE
MAX_PAGE_SIZE = support_inbox_sections.MAX_PAGE_SIZE
PREVIEW_LIMIT = support_inbox_sections.PREVIEW_LIMIT
SUPPORT_FILTERS = support_inbox_sections.SUPPORT_FILTERS
SUPPORT_QUEUE_FILTERS = support_inbox_sections.SUPPORT_QUEUE_FILTERS
SUPPORT_WAITING_STATE_LABELS = support_inbox_sections.SUPPORT_WAITING_STATE_LABELS
SUPPORT_INSIGHT_VIEWS = support_insight_sections.SUPPORT_INSIGHT_VIEWS

build_web_admin_support_payload = support_inbox_sections.build_web_admin_support_payload
_support_overview = support_inbox_sections._support_overview
build_web_admin_support_insights_payload = (
    support_insight_sections.build_web_admin_support_insights_payload
)
_build_web_admin_support_insights_payload_live = (
    support_insight_sections._build_web_admin_support_insights_payload_live
)
_normalize_support_insight_view = (
    support_insight_sections._normalize_support_insight_view
)
_support_insight_items_for_view = (
    support_insight_sections._support_insight_items_for_view
)
build_web_admin_support_ticket_payload = (
    support_ticket_sections.build_web_admin_support_ticket_payload
)
_serialize_support_ticket_triage_batch = (
    support_ticket_sections._serialize_support_ticket_triage_batch
)
