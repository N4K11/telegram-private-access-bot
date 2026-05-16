from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.admin_analytics_text import render_admin_analytics_text
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT,
    ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
    ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
    PAYLOAD_BUDGET_ADMIN_SUMMARY,
    QUERY_BUDGET_ADMIN_SUMMARY,
    timed_read_model_payload,
)
from app.services.analytics import build_analytics_snapshot
from app.services.web_admin_dashboard import build_web_admin_dashboard_payload
from app.services.web_admin_dashboard_analytics_sections import (
    build_web_admin_acquisition_payload,
    build_web_admin_conversion_payload,
    build_web_admin_pricing_payload,
    build_web_admin_promo_referral_payload,
)
from app.services.web_admin_dashboard_lifecycle_sections import (
    build_web_admin_lifecycle_payload,
)
from app.services.web_admin_dashboard_limits import ADMIN_DETAIL_DEFAULT_LIMIT
from app.services.web_admin_dashboard_read_model_descriptors import (
    READ_MODEL_GROUP_ANALYTICS,
    READ_MODEL_GROUP_LIFECYCLE,
    ReadModelDescriptor,
)
from app.services.web_admin_dashboard_summary_sections import (
    build_cabinet_admin_summary_payload,
)
from app.services.web_admin_dashboard_support_sections import (
    build_web_admin_support_insights_payload,
)


async def _build_live_admin_analytics_text_payload(
    session: AsyncSession,
    *,
    now: datetime,
) -> dict[str, object]:
    return await timed_read_model_payload(
        lambda: _build_live_admin_analytics_text_body(session, now=now),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_SUMMARY,
        payload_budget=PAYLOAD_BUDGET_ADMIN_SUMMARY,
        now=now,
    )


async def _build_live_admin_analytics_text_body(
    session: AsyncSession,
    *,
    now: datetime,
) -> dict[str, object]:
    analytics_snapshot = await build_analytics_snapshot(session, now=now)
    return {"text_body": render_admin_analytics_text(analytics_snapshot)}


async def _build_live_descriptor_payload(
    session: AsyncSession,
    *,
    descriptor: ReadModelDescriptor,
    settings: Settings,
    viewer_role: str,
    now: datetime,
) -> dict[str, object] | None:
    if descriptor.storage_group == READ_MODEL_GROUP_ANALYTICS:
        if descriptor.storage_key == ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY:
            return await build_cabinet_admin_summary_payload(
                session,
                settings=settings,
                now=now,
                source="live",
            )
        if descriptor.storage_key == ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT:
            return await _build_live_admin_analytics_text_payload(session, now=now)
        if descriptor.storage_key == ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING:
            return await build_web_admin_pricing_payload(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=ADMIN_DETAIL_DEFAULT_LIMIT,
                now=now,
                source="live",
            )
        if descriptor.storage_key == ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION:
            return await build_web_admin_acquisition_payload(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=ADMIN_DETAIL_DEFAULT_LIMIT,
                now=now,
                source="live",
            )
        if descriptor.storage_key == ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION:
            return await build_web_admin_conversion_payload(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=ADMIN_DETAIL_DEFAULT_LIMIT,
                now=now,
                source="live",
            )
        if descriptor.storage_key == ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL:
            return await build_web_admin_promo_referral_payload(
                session,
                settings=settings,
                viewer_role=viewer_role,
                limit=ADMIN_DETAIL_DEFAULT_LIMIT,
                now=now,
                source="live",
            )
        if descriptor.storage_key == ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD:
            role = (
                descriptor.scope_key.split(":", 1)[1]
                if descriptor.scope_key and descriptor.scope_key.startswith("role:")
                else viewer_role
            )
            return await build_web_admin_dashboard_payload(
                session,
                settings=settings,
                viewer_role=role,
                now=now,
                source="live",
            )
        return None
    if descriptor.storage_group == READ_MODEL_GROUP_LIFECYCLE:
        return await build_web_admin_lifecycle_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            view=descriptor.storage_key,
            limit=ADMIN_DETAIL_DEFAULT_LIMIT,
            now=now,
            source="live",
        )
    return await build_web_admin_support_insights_payload(
        session,
        settings=settings,
        viewer_role=viewer_role,
        view=descriptor.storage_key,
        limit=ADMIN_DETAIL_DEFAULT_LIMIT,
        now=now,
        source="live",
    )
