from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.analytics import build_analytics_snapshot
from app.services.web_admin_dashboard_lifecycle_attribution_serializers import (
    _build_lifecycle_attribution_view_items as _build_lifecycle_attribution_view_items,
)
from app.services.web_admin_dashboard_lifecycle_source_serializers import (
    _build_lifecycle_source_view_items as _build_lifecycle_source_view_items,
)
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
    clamp_admin_detail_limit,
)
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow

LIFECYCLE_VIEWS = {
    "rules": "Managed waves",
    "roi": "ROI",
    "sources": "Acquisition sources",
    "source_campaigns": "Source x campaign",
    "source_roi": "Source ROI",
    "source_opportunities": "Source opportunities",
    "source_actions": "Source actions",
    "source_highlights": "Source leaders",
    "source_watchlist": "Source watchlist",
    "highlights": "Highlights",
    "waves": "Wave modes",
    "families": "Touch families",
    "variants": "Campaign variants",
}

async def _build_web_admin_lifecycle_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    view: str = "rules",
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    analytics_snapshot=None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    normalized_view = view if view in LIFECYCLE_VIEWS else "rules"
    normalized_limit = clamp_admin_detail_limit(limit)
    snapshot = analytics_snapshot or await build_analytics_snapshot(session, now=current_time)
    attribution = snapshot.lifecycle_campaign_attribution

    source_view = _build_lifecycle_source_view_items(
        snapshot,
        attribution=attribution,
        view=normalized_view,
        limit=normalized_limit,
    )
    if source_view is not None:
        items, total_items = source_view
    else:
        items, total_items = _build_lifecycle_attribution_view_items(
            attribution,
            view=normalized_view,
            limit=normalized_limit,
        )

    return {
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "view": normalized_view,
        "view_label": LIFECYCLE_VIEWS[normalized_view],
        "available_views": [{"key": key, "label": label} for key, label in LIFECYCLE_VIEWS.items()],
        "limit": normalized_limit,
        "total_items": total_items,
        "total_sent_count": attribution.total_sent_count,
        "total_paid_users": attribution.total_paid_users,
        "total_payment_count": attribution.total_payment_count,
        "total_invite_issued_users": attribution.total_invite_issued_users,
        "revenue_total": attribution.revenue_total,
        "repeat_purchase_rate_percent": snapshot.repeat_purchase_rate_percent,
        "renewal_due_3d_users": snapshot.lifecycle_queues.renewal_due_3d_users,
        "renewal_due_1d_users": snapshot.lifecycle_queues.renewal_due_1d_users,
        "grace_period_users": snapshot.lifecycle_queues.grace_period_users,
        "win_back_ready_users": snapshot.lifecycle_queues.win_back_ready_users,
        "items": items,
    }
