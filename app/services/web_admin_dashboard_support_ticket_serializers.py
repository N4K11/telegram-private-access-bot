from __future__ import annotations

from app.services.web_admin_dashboard_common import _display_name as _display_name
from app.services.web_admin_dashboard_common import _dt as _dt
from app.services.web_admin_dashboard_common import _paginate as _paginate
from app.services.web_admin_dashboard_common import _payment_amount as _payment_amount
from app.services.web_admin_dashboard_common import _plain as _plain
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _build_support_operator_hints as _build_support_operator_hints,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _channel_name as _channel_name,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _hours_since as _hours_since,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _serialize_support_canned_replies as _serialize_support_canned_replies,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _serialize_support_next_action as _serialize_support_next_action,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _serialize_support_profile_summary as _serialize_support_profile_summary,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _serialize_support_ticket_pinned_context as _serialize_support_ticket_pinned_context,
)
from app.services.web_admin_dashboard_support_ticket_detail_serializers import (
    _tariff_name as _tariff_name,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _is_support_ticket_stale as _is_support_ticket_stale,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _matches_support_queue as _matches_support_queue,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _serialize_support_close_reason_analytics as _serialize_support_close_reason_analytics,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _serialize_support_ticket_list_item as _serialize_support_ticket_list_item,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _support_last_message_preview as _support_last_message_preview,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _support_queue_counts as _support_queue_counts,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _support_search_blob as _support_search_blob,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _support_waiting_state as _support_waiting_state,
)
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _truncate as _truncate,
)
