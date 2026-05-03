from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Channel
from app.runtime_state import snapshot_runtime_state
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
        "Оперативная сводка:",
        f"• Runtime: {'webhook' if settings.use_webhook else 'polling'}",
        f"• Mini App: {settings.mini_app_path}",
    ]
    badges: dict[str, int] = {}

    if has_permission(role, PERMISSION_SUPPORT):
        inbox = await build_admin_support_inbox(session, status="open", limit=1, now=current_time)
        lines.append(f"• Тикеты ждут ответа: {inbox.awaiting_admin_count}")
        lines.append(f"• Просрочено >24ч: {inbox.stale_open_count}")
        if inbox.awaiting_admin_count > 0:
            badges["support"] = inbox.awaiting_admin_count

    if has_permission(role, PERMISSION_CHANNELS) or has_permission(role, PERMISSION_DIAGNOSTICS):
        channel_risk_count = await _count_channel_risks(session)
        lines.append(f"• Каналы с рисками доступа: {channel_risk_count}")
        if channel_risk_count > 0:
            badges["diagnostics"] = channel_risk_count

    if has_permission(role, PERMISSION_OBSERVABILITY) or has_permission(role, PERMISSION_HEALTH):
        runtime = snapshot_runtime_state()
        critical_count = len(runtime.recent_critical_errors)
        lines.append(f"• Критических событий: {critical_count}")
        if runtime.last_backup_result_status:
            lines.append(f"• Last backup: {runtime.last_backup_result_status}")
        if runtime.last_telegram_api_error_at is not None and runtime.last_telegram_api_error:
            lines.append("• Telegram API error: yes")

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
