from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Tariff
from app.runtime_state import snapshot_runtime_state
from app.services import web_admin_dashboard_overview_sections as overview_sections
from app.services import web_admin_dashboard_support_sections as support_sections
from app.services.admin_roles import (
    PERMISSION_ANALYTICS,
    PERMISSION_BROADCASTS,
    PERMISSION_CHANNELS,
    PERMISSION_DIAGNOSTICS,
    PERMISSION_OBSERVABILITY,
    PERMISSION_PAYMENTS,
    PERMISSION_PROMOS,
    PERMISSION_SUPPORT,
    PERMISSION_TARIFFS,
    PERMISSION_USERS_VIEW,
    has_permission,
)
from app.services.admin_summary_previews import compact_admin_summary_payload
from app.services.analytics import build_analytics_snapshot
from app.services.observability import sanitize_observability_text
from app.services.offer_engine import build_offer_engine_snapshot
from app.services.web_admin_dashboard_analytics_sections import (
    _build_product_catalog_for_dashboard,
    _serialize_offer_inventory_preview,
    _serialize_pricing_intelligence_preview,
    _serialize_promo_attribution_summary,
    _serialize_referral_attribution_summary,
)
from app.services.web_admin_dashboard_common import PREVIEW_LIMIT
from app.services.web_admin_dashboard_directory_sections import (
    build_web_admin_payments_payload,
    build_web_admin_users_payload,
)
from app.services.web_admin_dashboard_lifecycle_sections import (
    _serialize_lifecycle_campaign_attribution,
    _serialize_lifecycle_offer_mix,
)
from app.utils.datetime import ensure_aware_utc, format_datetime

ADMIN_DASHBOARD_SECTION_KEYS = (
    "summary",
    "revenue_chart",
    "users_preview",
    "payments_preview",
    "crypto_invoices",
    "support",
    "promos",
    "tariffs",
    "broadcasts",
    "channels",
    "anomalies",
)


async def _build_web_admin_dashboard_payload_live(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    now: datetime,
    sections: tuple[str, ...] | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now)
    capabilities = _capabilities(viewer_role)
    normalized_sections = _normalize_dashboard_sections(sections)
    payload: dict[str, object] = {
        "generated_at_label": format_datetime(current_time, settings.timezone),
        "capabilities": capabilities,
    }
    if capabilities["analytics"] and _dashboard_section_requested(
        normalized_sections,
        "summary",
        "revenue_chart",
    ):
        snapshot = await build_analytics_snapshot(session, now=current_time)
        active_tariffs = await session.execute(
            select(Tariff)
            .options(selectinload(Tariff.channel))
            .where(Tariff.is_active.is_(True))
            .where(Tariff.archived_at.is_(None))
            .order_by(Tariff.sort_order.asc(), Tariff.id.asc())
        )
        offer_engine = build_offer_engine_snapshot(
            _build_product_catalog_for_dashboard(active_tariffs.scalars())
        )
        payload["summary"] = compact_admin_summary_payload(
            {
                "total_users": snapshot.total_users,
                "active_subscriptions": snapshot.active_subscriptions,
                "expired_users": snapshot.expired_users,
                "never_paid_users": snapshot.never_paid_users,
                "blocked_users": snapshot.blocked_users,
                "revenue_today": snapshot.revenue_today,
                "revenue_7_days": snapshot.revenue_7_days,
                "revenue_30_days": snapshot.revenue_30_days,
                "revenue_total": snapshot.revenue_total,
                "stars_payments": snapshot.stars_payments,
                "crypto_payments": snapshot.crypto_payments,
                "paid_users_total": snapshot.paid_users_total,
                "conversion_started": snapshot.conversion_started,
                "conversion_buy_viewed": snapshot.conversion_buy_viewed,
                "conversion_product_selected": snapshot.conversion_product_selected,
                "conversion_tariff_opened": snapshot.conversion_tariff_opened,
                "conversion_offer_clicked": snapshot.conversion_offer_clicked,
                "conversion_invoice_created": snapshot.conversion_invoice_created,
                "conversion_paid": snapshot.conversion_paid,
                "conversion_invite_issued": snapshot.conversion_invite_issued,
                "repeat_purchase_users": snapshot.repeat_purchase_users,
                "repeat_purchase_rate_percent": snapshot.repeat_purchase_rate_percent,
                "offer_inventory": _serialize_offer_inventory_preview(offer_engine),
                "pricing_intelligence": _serialize_pricing_intelligence_preview(
                    snapshot.pricing_intelligence
                ),
                "lifecycle_queues": {
                    "renewal_due_3d_users": snapshot.lifecycle_queues.renewal_due_3d_users,
                    "renewal_due_1d_users": snapshot.lifecycle_queues.renewal_due_1d_users,
                    "grace_period_users": snapshot.lifecycle_queues.grace_period_users,
                    "win_back_ready_users": snapshot.lifecycle_queues.win_back_ready_users,
                },
                "lifecycle_offer_mix": _serialize_lifecycle_offer_mix(
                    snapshot.lifecycle_offer_mix
                ),
                "lifecycle_campaign_attribution": _serialize_lifecycle_campaign_attribution(
                    snapshot.lifecycle_campaign_attribution
                ),
                "retention_segments": [
                    {
                        "segment": item.segment,
                        "label": item.label,
                        "candidate_count": item.candidate_count,
                        "recent_sent_count": item.recent_sent_count,
                        "dedupe_window_hours": item.dedupe_window_hours,
                    }
                    for item in snapshot.retention_segments
                ],
                "promo_attribution": _serialize_promo_attribution_summary(
                    snapshot.promo_attribution
                ),
                "referral_attribution": _serialize_referral_attribution_summary(
                    snapshot.referral_attribution
                ),
            }
        )
        payload["revenue_chart"] = [
            {
                "label": "Сегодня",
                "value": snapshot.revenue_today,
            },
            {"label": "7 дней", "value": snapshot.revenue_7_days},
            {"label": "30 дней", "value": snapshot.revenue_30_days},
            {"label": "Всего", "value": snapshot.revenue_total},
        ]
    if capabilities["users"] and _dashboard_section_requested(
        normalized_sections,
        "users_preview",
    ):
        payload["users_preview"] = await build_web_admin_users_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            page_size=PREVIEW_LIMIT,
            now=current_time,
        )
    if capabilities["payments"] and _dashboard_section_requested(
        normalized_sections,
        "payments_preview",
    ):
        payload["payments_preview"] = await build_web_admin_payments_payload(
            session,
            settings=settings,
            viewer_role=viewer_role,
            page_size=PREVIEW_LIMIT,
        )
    if capabilities["payments"] and _dashboard_section_requested(
        normalized_sections,
        "crypto_invoices",
    ):
        payload["crypto_invoices"] = await overview_sections._crypto_invoice_overview(
            session,
            settings=settings,
        )
    if capabilities["support"] and _dashboard_section_requested(
        normalized_sections,
        "support",
    ):
        payload["support"] = await support_sections._support_overview(
            session,
            settings=settings,
        )
    if capabilities["promos"] and _dashboard_section_requested(normalized_sections, "promos"):
        payload["promos"] = await overview_sections._promo_overview(
            session,
            settings=settings,
        )
    if capabilities["tariffs"] and _dashboard_section_requested(normalized_sections, "tariffs"):
        payload["tariffs"] = await overview_sections._tariff_overview(session)
    if capabilities["broadcasts"] and _dashboard_section_requested(
        normalized_sections,
        "broadcasts",
    ):
        payload["broadcasts"] = await overview_sections._broadcast_overview(
            session,
            settings=settings,
        )
    if (capabilities["diagnostics"] or capabilities["channels"]) and _dashboard_section_requested(
        normalized_sections,
        "channels",
    ):
        payload["channels"] = await overview_sections._channel_overview(session)
    if capabilities["observability"] and _dashboard_section_requested(
        normalized_sections,
        "anomalies",
    ):
        payload["anomalies"] = [
            {
                "event_name": item.event_name,
                "source": item.source,
                "message": sanitize_observability_text(item.message),
                "occurred_at_label": format_datetime(item.occurred_at, settings.timezone),
            }
            for item in snapshot_runtime_state().recent_critical_errors[:PREVIEW_LIMIT]
        ]
    if normalized_sections:
        payload["requested_sections"] = list(normalized_sections)
        return _filter_dashboard_payload_sections(payload, sections=normalized_sections)
    return payload


def _capabilities(role: str) -> dict[str, bool]:
    return {
        "analytics": has_permission(role, PERMISSION_ANALYTICS),
        "users": has_permission(role, PERMISSION_USERS_VIEW),
        "payments": has_permission(role, PERMISSION_PAYMENTS),
        "support": has_permission(role, PERMISSION_SUPPORT),
        "promos": has_permission(role, PERMISSION_PROMOS),
        "tariffs": has_permission(role, PERMISSION_TARIFFS),
        "broadcasts": has_permission(role, PERMISSION_BROADCASTS),
        "diagnostics": has_permission(role, PERMISSION_DIAGNOSTICS),
        "observability": has_permission(role, PERMISSION_OBSERVABILITY),
        "channels": has_permission(role, PERMISSION_CHANNELS),
    }


def _normalize_dashboard_sections(
    sections: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if not sections:
        return ()
    normalized: list[str] = []
    for item in sections:
        key = str(item or "").strip()
        if not key or key not in ADMIN_DASHBOARD_SECTION_KEYS or key in normalized:
            continue
        normalized.append(key)
    return tuple(normalized)


def _dashboard_section_requested(sections: tuple[str, ...], *keys: str) -> bool:
    if not sections:
        return True
    return any(key in sections for key in keys)


def _filter_dashboard_payload_sections(
    payload: dict[str, object],
    *,
    sections: tuple[str, ...],
) -> dict[str, object]:
    if not sections:
        return payload
    filtered: dict[str, object] = {}
    always_include = {
        "generated_at",
        "generated_at_label",
        "source",
        "build_duration_ms",
        "staleness_seconds",
        "capabilities",
    }
    for key, value in payload.items():
        if key in always_include or key in sections:
            filtered[key] = value
    filtered["requested_sections"] = list(sections)
    return filtered
