from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AuditLog, Payment, Subscription, User
from app.runtime_state import snapshot_runtime_state
from app.services.admin_read_model_reporting import (
    AdminReadModelActionSummary,
    AdminReadModelDriftSummary,
    AdminReadModelWatchlistSummary,
    build_admin_read_model_action_digest,
    build_admin_read_model_action_summary,
    build_admin_read_model_drift_digest,
    build_admin_read_model_drift_summary,
    build_admin_read_model_operator_digest,
    build_admin_read_model_watchlist_digest,
    build_admin_read_model_watchlist_summary,
)
from app.services.audit import write_audit_log
from app.services.payments.crypto_pay import CRYPTO_PAY_PROVIDER, MINOR_UNITS_MULTIPLIER
from app.services.payments.stars import STARS_PROVIDER
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow

logger = logging.getLogger(__name__)

REPORT_PERIOD_DAILY = "daily"
REPORT_PERIOD_WEEKLY = "weekly"
REPORT_DISPATCH_HOUR = 9
ACTION_REPORT_SENT_DAILY = "admin_report_sent_daily"
ACTION_REPORT_SENT_WEEKLY = "admin_report_sent_weekly"
ZERO_DECIMAL = Decimal("0")
DAILY_REPORT_LABEL = (
    "\u0415\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u044b\u0439 "
    "\u043e\u0442\u0447\u0451\u0442"
)
WEEKLY_REPORT_LABEL = (
    "\u0415\u0436\u0435\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u044b\u0439 "
    "\u043e\u0442\u0447\u0451\u0442"
)
TEXT_NEW_USERS = (
    "\u041d\u043e\u0432\u044b\u0445 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430"
    "\u0442\u0435\u043b\u0435\u0439: "
)
TEXT_ACTIVE_SUBSCRIPTIONS = (
    "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438"
    "\u0441\u043e\u043a: "
)
TEXT_EXPIRED_SUBSCRIPTIONS = (
    "\u0418\u0441\u0442\u0435\u043a\u043b\u043e \u0437\u0430 \u043f\u0435\u0440\u0438"
    "\u043e\u0434: "
)
TEXT_ANOMALIES = "\u0410\u043d\u043e\u043c\u0430\u043b\u0438\u0439: "
TEXT_PERIOD = "\u041f\u0435\u0440\u0438\u043e\u0434: "


@dataclass(frozen=True, slots=True)
class AdminReportSnapshot:
    period: str
    period_key: str
    label: str
    range_start: datetime
    range_end: datetime
    generated_at: datetime
    new_users: int
    payments_count: int
    stars_revenue: int
    crypto_revenue: dict[str, Decimal]
    active_subscriptions: int
    expired_subscriptions: int
    anomalies: int
    read_model_watchlist_summary: AdminReadModelWatchlistSummary | None = None
    read_model_action_summary: AdminReadModelActionSummary | None = None
    read_model_drift_summary: AdminReadModelDriftSummary | None = None


@dataclass(frozen=True, slots=True)
class ScheduledReportDispatchResult:
    sent_periods: tuple[str, ...] = ()
    skipped_periods: tuple[str, ...] = ()
    not_due: bool = False

    @property
    def has_sent_reports(self) -> bool:
        return bool(self.sent_periods)


async def build_admin_report(
    session: AsyncSession,
    *,
    period: str,
    timezone: str,
    settings: Settings | None = None,
    viewer_role: str = "owner",
    now: datetime | None = None,
) -> AdminReportSnapshot:
    current_time = ensure_aware_utc(now or utcnow())
    zone = ZoneInfo(timezone)
    local_now = current_time.astimezone(zone)

    if period == REPORT_PERIOD_DAILY:
        label = DAILY_REPORT_LABEL
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_key = local_start.date().isoformat()
    elif period == REPORT_PERIOD_WEEKLY:
        label = WEEKLY_REPORT_LABEL
        local_start = (local_now - timedelta(days=7)).replace(microsecond=0)
        period_key = f"{local_now.isocalendar().year}-W{local_now.isocalendar().week:02d}"
    else:
        raise ValueError(f"Unsupported report period: {period}")

    range_start = local_start.astimezone(UTC)
    range_end = current_time

    new_users = int(
        (
            await session.execute(
                select(func.count(User.id))
                .where(User.created_at >= range_start)
                .where(User.created_at <= range_end)
            )
        ).scalar_one()
        or 0
    )

    payment_rows = list(
        (
            await session.execute(
                select(Payment.provider, Payment.currency, Payment.amount)
                .where(Payment.status == "paid")
                .where(Payment.paid_at.is_not(None))
                .where(Payment.paid_at >= range_start)
                .where(Payment.paid_at <= range_end)
            )
        ).all()
    )
    payments_count = len(payment_rows)
    stars_revenue = sum(
        int(amount)
        for provider, _, amount in payment_rows
        if provider == STARS_PROVIDER
    )
    crypto_revenue: dict[str, Decimal] = defaultdict(lambda: ZERO_DECIMAL)
    for provider, currency, amount in payment_rows:
        if provider.startswith(CRYPTO_PAY_PROVIDER):
            crypto_revenue[str(currency)] += Decimal(amount) / MINOR_UNITS_MULTIPLIER

    active_subscriptions = int(
        (
            await session.execute(
                select(func.count(Subscription.id))
                .where(Subscription.status == "active")
                .where(Subscription.revoked_at.is_(None))
                .where(Subscription.expires_at > current_time)
            )
        ).scalar_one()
        or 0
    )

    expired_subscriptions = int(
        (
            await session.execute(
                select(func.count(Subscription.id))
                .where(Subscription.expires_at >= range_start)
                .where(Subscription.expires_at <= range_end)
            )
        ).scalar_one()
        or 0
    )

    runtime = snapshot_runtime_state()
    anomalies = sum(
        1 for item in runtime.recent_critical_errors if item.occurred_at >= range_start
    )

    read_model_watchlist_summary = None
    read_model_action_summary = None
    read_model_drift_summary = None
    if settings is not None:
        read_model_watchlist_summary = await build_admin_read_model_watchlist_summary(
            session,
            settings=settings,
            viewer_role=viewer_role,
            now=current_time,
            limit=3,
            source="snapshot",
        )
        read_model_action_summary = await build_admin_read_model_action_summary(
            session,
            settings=settings,
            viewer_role=viewer_role,
            now=current_time,
            limit=5,
            source="live",
        )
        read_model_drift_summary = await build_admin_read_model_drift_summary(
            session,
            settings=settings,
            viewer_role=viewer_role,
            now=current_time,
            limit=5,
        )

    return AdminReportSnapshot(
        period=period,
        period_key=period_key,
        label=label,
        range_start=range_start,
        range_end=range_end,
        generated_at=current_time,
        new_users=new_users,
        payments_count=payments_count,
        stars_revenue=stars_revenue,
        crypto_revenue=dict(sorted(crypto_revenue.items())),
        active_subscriptions=active_subscriptions,
        expired_subscriptions=expired_subscriptions,
        anomalies=anomalies,
        read_model_watchlist_summary=read_model_watchlist_summary,
        read_model_action_summary=read_model_action_summary,
        read_model_drift_summary=read_model_drift_summary,
    )


def render_admin_report(snapshot: AdminReportSnapshot, *, timezone: str) -> str:
    lines = [f"\U0001f4ca {snapshot.label}", ""]
    lines.append(f"{TEXT_NEW_USERS}{snapshot.new_users}")
    lines.append(f"\u041e\u043f\u043b\u0430\u0442: {snapshot.payments_count}")
    lines.append(f"Stars: {snapshot.stars_revenue}")
    lines.append(f"Crypto: {_format_crypto_totals(snapshot.crypto_revenue)}")
    lines.append(f"{TEXT_ACTIVE_SUBSCRIPTIONS}{snapshot.active_subscriptions}")
    lines.append(f"{TEXT_EXPIRED_SUBSCRIPTIONS}{snapshot.expired_subscriptions}")
    lines.append(f"{TEXT_ANOMALIES}{snapshot.anomalies}")
    if snapshot.read_model_watchlist_summary is not None:
        watchlist_digest = build_admin_read_model_watchlist_digest(
            snapshot.read_model_watchlist_summary,
            max_items=0,
        )
        lines.append(f"Read-model watchlist: {watchlist_digest.summary_line}")
        if watchlist_digest.top_label:
            lines.append(f"Top watch item: {watchlist_digest.top_label}")
        if watchlist_digest.top_detail:
            lines.append(f"Watch note: {watchlist_digest.top_detail}")
        if watchlist_digest.item_lines:
            lines.append("Read-model watchlist digest:")
            for item_line in watchlist_digest.item_lines:
                lines.append(f"- {item_line}")
    operator_digest = build_admin_read_model_operator_digest(
        watchlist_summary=snapshot.read_model_watchlist_summary,
        action_summary=snapshot.read_model_action_summary,
        drift_summary=snapshot.read_model_drift_summary,
    )
    if operator_digest is not None:
        lines.append(f"Read-model summary: {operator_digest.summary_line}")
    if snapshot.read_model_action_summary is not None:
        action_digest = build_admin_read_model_action_digest(
            snapshot.read_model_action_summary,
            max_items=0,
        )
        lines.append(
            f"Read-models: {action_digest.summary_line}"
        )
        if action_digest.top_label:
            lines.append(
                "Top read-model action: "
                f"{action_digest.top_label}"
            )
        if action_digest.top_detail:
            lines.append(f"Action note: {action_digest.top_detail}")
        if action_digest.item_lines:
            lines.append("Read-model digest:")
            for item_line in action_digest.item_lines:
                lines.append(f"- {item_line}")
    if snapshot.read_model_drift_summary is not None:
        drift_digest = build_admin_read_model_drift_digest(
            snapshot.read_model_drift_summary,
            max_items=0,
        )
        lines.append(
            f"Read-model drift: {drift_digest.extended_summary_line}"
        )
        if drift_digest.top_label:
            lines.append(
                "Top drift regression: "
                f"{drift_digest.top_label}"
            )
        if snapshot.read_model_drift_summary.top_budget_regression_label:
            lines.append(
                "Top budget regression: "
                f"{snapshot.read_model_drift_summary.top_budget_regression_label}"
            )
        if drift_digest.item_lines:
            lines.append("Read-model drift digest:")
            for item_line in drift_digest.item_lines:
                lines.append(f"- {item_line}")
    lines.extend(
        [
            "",
            (
                f"{TEXT_PERIOD}{format_datetime(snapshot.range_start, timezone)} "
                f"\u2014 {format_datetime(snapshot.range_end, timezone)}"
            ),
        ]
    )
    return "\n".join(lines)


async def dispatch_scheduled_admin_reports(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> ScheduledReportDispatchResult:
    current_time = ensure_aware_utc(now or utcnow())
    local_now = current_time.astimezone(ZoneInfo(settings.timezone))
    if local_now.hour != REPORT_DISPATCH_HOUR or not settings.admin_ids_set:
        return ScheduledReportDispatchResult(not_due=True)

    sent_periods: list[str] = []
    skipped_periods: list[str] = []

    if await _maybe_dispatch_period(
        session=session,
        bot=bot,
        settings=settings,
        period=REPORT_PERIOD_DAILY,
        now=current_time,
    ):
        sent_periods.append(REPORT_PERIOD_DAILY)
    else:
        skipped_periods.append(REPORT_PERIOD_DAILY)

    if local_now.weekday() == 0:
        if await _maybe_dispatch_period(
            session=session,
            bot=bot,
            settings=settings,
            period=REPORT_PERIOD_WEEKLY,
            now=current_time,
        ):
            sent_periods.append(REPORT_PERIOD_WEEKLY)
        else:
            skipped_periods.append(REPORT_PERIOD_WEEKLY)

    return ScheduledReportDispatchResult(
        sent_periods=tuple(sent_periods),
        skipped_periods=tuple(skipped_periods),
    )


async def _maybe_dispatch_period(
    *,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    period: str,
    now: datetime,
) -> bool:
    snapshot = await build_admin_report(
        session,
        period=period,
        timezone=settings.timezone,
        settings=settings,
        now=now,
    )
    action = (
        ACTION_REPORT_SENT_DAILY
        if period == REPORT_PERIOD_DAILY
        else ACTION_REPORT_SENT_WEEKLY
    )
    if await _report_already_sent(session, action=action, period_key=snapshot.period_key):
        return False

    text = render_admin_report(snapshot, timezone=settings.timezone)
    delivered_admin_ids: list[int] = []
    for admin_id in sorted(settings.admin_ids_set):
        try:
            await bot.send_message(admin_id, text)
            delivered_admin_ids.append(admin_id)
        except Exception:
            logger.exception(
                "Failed to deliver %s report to admin %s",
                period,
                admin_id,
            )

    if not delivered_admin_ids:
        return False

    await write_audit_log(
        session,
        action=action,
        payload={
            "period": period,
            "period_key": snapshot.period_key,
            "delivered_admin_ids": delivered_admin_ids,
        },
    )
    await session.commit()
    return True


async def _report_already_sent(
    session: AsyncSession,
    *,
    action: str,
    period_key: str,
) -> bool:
    payload_rows = list(
        (
            await session.execute(
                select(AuditLog.payload).where(AuditLog.action == action)
            )
        ).scalars()
    )
    for raw_payload in payload_rows:
        if not raw_payload:
            continue
        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError:
            continue
        if parsed.get("period_key") == period_key:
            return True
    return False


def _format_crypto_totals(values: dict[str, Decimal]) -> str:
    if not values:
        return "0"
    parts = [
        f"{_format_decimal(amount)} {currency}"
        for currency, amount in values.items()
    ]
    return " / ".join(parts)


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01"))
    return format(normalized, "f").rstrip("0").rstrip(".") or "0"
