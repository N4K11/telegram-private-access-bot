from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.admin_read_model_reporting import (
    build_admin_read_model_snapshot_digest_payload,
    build_admin_read_model_snapshot_focus_payload,
    build_admin_read_model_snapshot_operator_payload,
)
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
    ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
    PAYLOAD_BUDGET_ADMIN_DASHBOARD,
    QUERY_BUDGET_ADMIN_DASHBOARD,
    load_analytics_fact_payload,
    normalize_read_model_source,
    timed_read_model_payload,
)
from app.services.web_admin_dashboard_dashboard_sections import (
    _build_web_admin_dashboard_payload_live,
    _filter_dashboard_payload_sections,
    _normalize_dashboard_sections,
)
from app.utils.datetime import ensure_aware_utc, utcnow


async def build_web_admin_dashboard_payload(
    session: AsyncSession,
    *,
    settings: Settings,
    viewer_role: str,
    now: datetime | None = None,
    source: str = "snapshot",
    sections: tuple[str, ...] | None = None,
) -> dict[str, object]:
    current_time = ensure_aware_utc(now or utcnow())
    normalized_source = normalize_read_model_source(source)
    normalized_sections = _normalize_dashboard_sections(sections)
    if normalized_source != "live":
        snapshot_payload = await load_analytics_fact_payload(
            session,
            fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
            fact_date=current_time.date(),
            scope_key=f"role:{viewer_role}",
            now=current_time,
        )
        if snapshot_payload is not None:
            summary_payload = snapshot_payload.get("summary")
            include_summary = not normalized_sections or "summary" in normalized_sections
            if include_summary and isinstance(summary_payload, dict):
                read_models_snapshot = await load_analytics_fact_payload(
                    session,
                    fact_key=ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS,
                    fact_date=current_time.date(),
                    now=current_time,
                )
                read_model_focus = build_admin_read_model_snapshot_focus_payload(
                    read_models_snapshot,
                )
                read_model_digest = build_admin_read_model_snapshot_digest_payload(
                    read_models_snapshot,
                )
                read_model_operator_summary = (
                    build_admin_read_model_snapshot_operator_payload(
                        read_models_snapshot,
                    )
                )
                updated_summary = dict(summary_payload)
                if read_model_focus is not None:
                    updated_summary["read_model_focus"] = read_model_focus
                if read_model_operator_summary is not None:
                    updated_summary["read_model_operator_summary"] = (
                        read_model_operator_summary
                    )
                if read_model_digest is not None:
                    updated_summary["read_model_digest"] = read_model_digest
                if updated_summary != summary_payload:
                    snapshot_payload = dict(snapshot_payload)
                    snapshot_payload["summary"] = updated_summary
            return _filter_dashboard_payload_sections(
                snapshot_payload,
                sections=normalized_sections,
            )
    return await timed_read_model_payload(
        lambda: _build_web_admin_dashboard_payload_live(
            session,
            settings=settings,
            viewer_role=viewer_role,
            now=current_time,
            sections=normalized_sections,
        ),
        session=session,
        query_budget=QUERY_BUDGET_ADMIN_DASHBOARD,
        payload_budget=PAYLOAD_BUDGET_ADMIN_DASHBOARD,
        now=current_time,
    )
