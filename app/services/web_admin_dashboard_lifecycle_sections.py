from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.admin_read_models import (
    PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
    QUERY_BUDGET_ADMIN_LIFECYCLE,
    load_lifecycle_fact_payload,
    normalize_read_model_source,
    timed_read_model_payload,
)
from app.services.web_admin_dashboard_lifecycle_live import (
    LIFECYCLE_VIEWS,
    _build_web_admin_lifecycle_payload_live,
)
from app.services.web_admin_dashboard_lifecycle_serializers import (
    _serialize_lifecycle_campaign_attribution as _serialize_lifecycle_campaign_attribution,
)
from app.services.web_admin_dashboard_lifecycle_serializers import (
    _serialize_lifecycle_offer_mix as _serialize_lifecycle_offer_mix,
)
from app.services.web_admin_dashboard_limits import (
    ADMIN_DETAIL_DEFAULT_LIMIT,
)
from app.utils.datetime import ensure_aware_utc, utcnow


async def build_web_admin_lifecycle_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    view: str = "rules",
    limit: int = ADMIN_DETAIL_DEFAULT_LIMIT,
    now: datetime | None = None,
    source: str = "snapshot",
) -> dict[str, object]:
    del viewer_role
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    normalized_view = view if view in LIFECYCLE_VIEWS else "rules"
    if normalized_source != "live":
        snapshot_payload = await load_lifecycle_fact_payload(
            session,
            view_key=normalized_view,
            now=current_time,
        )
        if snapshot_payload is not None:
            return snapshot_payload
    return await timed_read_model_payload(
        lambda: _build_web_admin_lifecycle_payload_live(
            session,
            settings=settings,
            view=normalized_view,
            limit=limit,
            now=current_time,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_LIFECYCLE,
        payload_budget=PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
        now=current_time,
    )
