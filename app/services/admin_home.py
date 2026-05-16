from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Channel
from app.runtime_state import snapshot_runtime_state
from app.services.admin_read_model_reporting import (
    build_admin_read_model_action_summary,
    build_admin_read_model_drift_summary,
    build_admin_read_model_operator_digest,
    build_admin_read_model_watchlist_summary,
    load_admin_read_model_alert_summary,
)
from app.services.admin_roles import (
    PERMISSION_CHANNELS,
    PERMISSION_DIAGNOSTICS,
    PERMISSION_HEALTH,
    PERMISSION_OBSERVABILITY,
    PERMISSION_SUPPORT,
    has_permission,
)
from app.services.support import build_admin_support_inbox
from app.utils.datetime import ensure_aware_utc, utcnow


@dataclass(frozen=True, slots=True)
class AdminHomeSnapshot:
    summary_block: str
    section_badges: dict[str, int]


async def build_admin_home_snapshot(
    session: AsyncSession,
    *,
    role: str,
    settings: Settings,
    now: datetime | None = None,
) -> AdminHomeSnapshot:
    current_time = ensure_aware_utc(now or utcnow())
    lines = [
        "Admin home:",
        f"- Runtime: {'webhook' if settings.use_webhook else 'polling'}",
        f"- Mini App: {settings.mini_app_path}",
    ]
    badges: dict[str, int] = {}

    if has_permission(role, PERMISSION_SUPPORT):
        inbox = await build_admin_support_inbox(session, status="open", limit=1, now=current_time)
        awaiting_label = "- Support awaiting admin: "
        stale_label = "- Stale support tickets >24h: "
        lines.append(f"{awaiting_label}{inbox.awaiting_admin_count}")
        lines.append(f"{stale_label}{inbox.stale_open_count}")
        if inbox.awaiting_admin_count > 0:
            badges["support"] = inbox.awaiting_admin_count

    if has_permission(role, PERMISSION_CHANNELS) or has_permission(role, PERMISSION_DIAGNOSTICS):
        channel_risk_count = await _count_channel_risks(session)
        channel_risk_label = "- Channels with permission risks: "
        lines.append(f"{channel_risk_label}{channel_risk_count}")
        if channel_risk_count > 0:
            badges["diagnostics"] = channel_risk_count

    if has_permission(role, PERMISSION_OBSERVABILITY) or has_permission(role, PERMISSION_HEALTH):
        runtime = snapshot_runtime_state()
        critical_count = len(runtime.recent_critical_errors)
        critical_label = "- Critical events: "
        lines.append(f"{critical_label}{critical_count}")
        if runtime.last_backup_result_status:
            lines.append(f"- Last backup: {runtime.last_backup_result_status}")
        if runtime.last_telegram_api_error_at is not None and runtime.last_telegram_api_error:
            lines.append("- Telegram API error: yes")

    if has_permission(role, PERMISSION_OBSERVABILITY) or has_permission(role, PERMISSION_HEALTH):
        read_model_summary = await load_admin_read_model_alert_summary(
            session,
            now=current_time,
        )
        if read_model_summary is None:
            lines.append("- Read-model snapshots: missing")
        else:
            lines.append(
                "- Read-model alerts: "
                f"{read_model_summary.alert_count} "
                f"(stale {read_model_summary.stale_count} / "
                f"missing {read_model_summary.missing_count} / "
                f"budget {read_model_summary.budget_exceeded_count})"
            )
            watchlist_summary = await build_admin_read_model_watchlist_summary(
                session,
                settings=settings,
                viewer_role=role,
                now=current_time,
                limit=3,
                source="snapshot",
            )
            action_summary = await build_admin_read_model_action_summary(
                session,
                settings=settings,
                viewer_role=role,
                now=current_time,
                limit=3,
                source="snapshot",
            )
            drift_summary = await build_admin_read_model_drift_summary(
                session,
                settings=settings,
                viewer_role=role,
                now=current_time,
                limit=3,
            )
            operator_digest = build_admin_read_model_operator_digest(
                watchlist_summary=watchlist_summary,
                action_summary=action_summary,
                drift_summary=drift_summary,
            )
            if operator_digest is not None:
                lines.append(
                    "- Read-model summary: "
                    f"{operator_digest.summary_line}"
                )

    return AdminHomeSnapshot(summary_block="\n".join(lines), section_badges=badges)


async def _count_channel_risks(session: AsyncSession) -> int:
    statement = (
        select(func.count(Channel.id))
        .where(Channel.is_active.is_(True))
        .where(
            or_(
                Channel.invite_users_permission.is_(False),
                Channel.ban_users_permission.is_(False),
            )
        )
    )
    return int((await session.execute(statement)).scalar_one() or 0)
