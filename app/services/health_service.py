from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import BackupRecord, Channel, Payment, Subscription, User
from app.runtime_state import snapshot_runtime_state
from app.utils.datetime import ensure_aware_utc, format_datetime, resolve_timezone, utcnow

MetricStatus = Literal["ok", "fail", "info", "warn"]
_STATUS_ICONS: dict[MetricStatus, str] = {
    "ok": "✅",
    "fail": "❌",
    "info": "ℹ️",
    "warn": "⚠️",
}


@dataclass(frozen=True, slots=True)
class HealthMetric:
    label: str
    status: MetricStatus
    details: str


@dataclass(frozen=True, slots=True)
class AdminHealthReport:
    metrics: tuple[HealthMetric, ...]
    summary_ok: bool


@dataclass(frozen=True, slots=True)
class StoreProbeResult:
    readable: bool
    writable: bool
    read_error: str | None = None
    write_error: str | None = None


@dataclass(frozen=True, slots=True)
class _HealthCounts:
    users_count: int
    active_subscriptions_count: int
    payments_today_count: int


async def build_admin_health_report(
    session: AsyncSession,
    bot,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> AdminHealthReport:
    current_time = ensure_aware_utc(now or utcnow())
    runtime = snapshot_runtime_state()
    metrics: list[HealthMetric] = []

    metrics.append(
        HealthMetric(
            label="Аптайм",
            status="info",
            details=_format_uptime(runtime.started_at, current_time),
        )
    )

    try:
        bot_user = await bot.get_me()
        username = getattr(bot_user, "username", None)
        bot_label = f"@{escape(username)}" if username else f"id={getattr(bot_user, 'id', '—')}"
        metrics.append(HealthMetric(label="Бот подключен", status="ok", details=bot_label))
    except Exception as exc:
        metrics.append(
            HealthMetric(
                label="Бот подключен",
                status="fail",
                details=escape(_short_error(exc)),
            )
        )

    channels = await _load_channels(session)
    active_channels = [channel for channel in channels if channel.is_active]
    if active_channels:
        details = _render_channel_summary(active_channels, len(channels))
        metrics.append(HealthMetric(label="Каналы настроены", status="ok", details=details))
    else:
        metrics.append(
            HealthMetric(
                label="Каналы настроены",
                status="fail",
                details="нет активных каналов в базе",
            )
        )

    store_probe = await _probe_store_health(session)
    read_details = "OK"
    if not store_probe.readable:
        read_details = escape(store_probe.read_error or "недоступно")
    metrics.append(
        HealthMetric(
            label="Хранилище: чтение",
            status="ok" if store_probe.readable else "fail",
            details=read_details,
        )
    )

    write_details = "OK"
    if not store_probe.writable:
        write_details = escape(store_probe.write_error or "недоступно")
    metrics.append(
        HealthMetric(
            label="Хранилище: запись",
            status="ok" if store_probe.writable else "fail",
            details=write_details,
        )
    )

    if store_probe.readable:
        counts = await _load_counts(session, current_time, settings.timezone)
        metrics.extend(
            (
                HealthMetric(label="Пользователи", status="info", details=str(counts.users_count)),
                HealthMetric(
                    label="Активные подписки",
                    status="info",
                    details=str(counts.active_subscriptions_count),
                ),
                HealthMetric(
                    label="Ожидающие join requests",
                    status="info",
                    details="0 (в текущем flow не используются)",
                ),
                HealthMetric(
                    label="Платежей сегодня",
                    status="info",
                    details=str(counts.payments_today_count),
                ),
            )
        )
    else:
        metrics.extend(
            (
                HealthMetric(label="Пользователи", status="warn", details="недоступно"),
                HealthMetric(label="Активные подписки", status="warn", details="недоступно"),
                HealthMetric(
                    label="Ожидающие join requests",
                    status="warn",
                    details="недоступно",
                ),
                HealthMetric(label="Платежей сегодня", status="warn", details="недоступно"),
            )
        )

    metrics.append(
        HealthMetric(
            label="Последний update",
            status="info" if runtime.last_update_at is not None else "warn",
            details=_render_last_update(runtime, settings.timezone),
        )
    )
    metrics.append(
        HealthMetric(
            label="Последний maintenance run",
            status="info" if runtime.last_maintenance_run_at is not None else "warn",
            details=_render_last_maintenance(runtime, settings.timezone),
        )
    )
    metrics.append(
        HealthMetric(
            label="Последняя Telegram API ошибка",
            status="warn" if runtime.last_telegram_api_error else "info",
            details=_render_last_telegram_error(runtime, settings.timezone),
        )
    )

    last_backup_time = await _load_last_backup_time(session)
    if not settings.backup_enabled:
        backup_status: MetricStatus = "info"
        backup_details = "backup disabled"
    elif last_backup_time is None:
        backup_status = "warn"
        backup_details = "ещё не создавался"
    else:
        backup_status = "info"
        backup_details = format_datetime(last_backup_time, settings.timezone)
    metrics.append(
        HealthMetric(
            label="Последний backup",
            status=backup_status,
            details=backup_details,
        )
    )

    summary_ok = all(metric.status != "fail" for metric in metrics)
    return AdminHealthReport(metrics=tuple(metrics), summary_ok=summary_ok)


def render_admin_health_report(report: AdminHealthReport) -> str:
    lines = ["❤️ Состояние бота", ""]
    for metric in report.metrics:
        lines.append(f"{_STATUS_ICONS[metric.status]} {metric.label}: {metric.details}")
    lines.append("")
    if report.summary_ok:
        lines.append("Итог: всё работает штатно.")
    else:
        lines.append("Итог: есть проблемы, проверьте строки с ❌.")
    return "\n".join(lines)


async def _load_channels(session: AsyncSession) -> list[Channel]:
    result = await session.execute(
        select(Channel).order_by(Channel.is_active.desc(), Channel.id.asc())
    )
    return list(result.scalars())


async def _probe_store_health(session: AsyncSession) -> StoreProbeResult:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        await session.rollback()
        message = _short_error(exc)
        return StoreProbeResult(
            readable=False,
            writable=False,
            read_error=message,
            write_error=message,
        )

    try:
        await session.execute(text("UPDATE users SET is_blocked = is_blocked WHERE 1 = 0"))
    except Exception as exc:
        await session.rollback()
        return StoreProbeResult(
            readable=True,
            writable=False,
            write_error=_short_error(exc),
        )

    await session.rollback()
    return StoreProbeResult(readable=True, writable=True)


async def _load_counts(
    session: AsyncSession,
    current_time: datetime,
    timezone: str,
) -> _HealthCounts:
    users_count = await _scalar_count(session, select(func.count(User.id)))
    active_subscriptions_count = await _scalar_count(
        session,
        select(func.count(Subscription.id))
        .where(Subscription.status == "active")
        .where(Subscription.revoked_at.is_(None))
        .where(Subscription.expires_at > current_time),
    )

    timezone_info = resolve_timezone(timezone)
    local_now = current_time.astimezone(timezone_info)
    start_of_day_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(UTC)
    end_of_day_utc = (start_of_day_local + timedelta(days=1)).astimezone(UTC)
    payments_today_count = await _scalar_count(
        session,
        select(func.count(Payment.id))
        .where(Payment.status == "paid")
        .where(Payment.paid_at.is_not(None))
        .where(Payment.paid_at >= start_of_day_utc)
        .where(Payment.paid_at < end_of_day_utc),
    )

    return _HealthCounts(
        users_count=users_count,
        active_subscriptions_count=active_subscriptions_count,
        payments_today_count=payments_today_count,
    )


async def _scalar_count(session: AsyncSession, statement) -> int:
    result = await session.execute(statement)
    value = result.scalar_one()
    return int(value or 0)


async def _load_last_backup_time(session: AsyncSession) -> datetime | None:
    result = await session.execute(
        select(BackupRecord.created_at)
        .order_by(BackupRecord.created_at.desc(), BackupRecord.id.desc())
        .limit(1)
    )
    value = result.scalar_one_or_none()
    return ensure_aware_utc(value) if value is not None else None


def _render_channel_summary(active_channels: list[Channel], total_channels: int) -> str:
    references = ", ".join(
        f"<code>{channel.telegram_chat_id}</code>" for channel in active_channels[:3]
    )
    if len(active_channels) > 3:
        references += ", …"
    return f"{len(active_channels)} активных / {total_channels} всего · {references}"


def _render_last_update(runtime, timezone: str) -> str:
    if runtime.last_update_at is None:
        return "ещё нет данных"

    parts: list[str] = []
    if runtime.last_update_id is not None:
        parts.append(f"<code>{runtime.last_update_id}</code>")
    if runtime.last_update_kind:
        parts.append(escape(runtime.last_update_kind))
    parts.append(format_datetime(runtime.last_update_at, timezone))
    return " · ".join(parts)


def _render_last_maintenance(runtime, timezone: str) -> str:
    if runtime.last_maintenance_run_at is None:
        return "ещё не выполнялся"

    details = format_datetime(runtime.last_maintenance_run_at, timezone)
    if runtime.last_maintenance_label:
        details += f" · {escape(runtime.last_maintenance_label)}"
    return details


def _render_last_telegram_error(runtime, timezone: str) -> str:
    if not runtime.last_telegram_api_error or runtime.last_telegram_api_error_at is None:
        return "не было"
    return (
        f"{format_datetime(runtime.last_telegram_api_error_at, timezone)}"
        f" · {escape(runtime.last_telegram_api_error)}"
    )


def _format_uptime(started_at: datetime | None, current_time: datetime) -> str:
    if started_at is None:
        return "ещё не зафиксирован"

    delta = max(current_time - ensure_aware_utc(started_at), timedelta())
    total_seconds = int(delta.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}д")
    if hours or days:
        parts.append(f"{hours}ч")
    if minutes or hours or days:
        parts.append(f"{minutes}м")
    else:
        parts.append(f"{seconds}с")
    return " ".join(parts)


def _short_error(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__
