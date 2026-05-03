from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_users import admin_analytics_keyboard
from app.bot.routers.common import edit_or_answer
from app.services.admin_roles import PERMISSION_ANALYTICS
from app.services.analytics import (
    AnalyticsSnapshot,
    ProductFunnelSnapshot,
    build_analytics_snapshot,
)

router = Router(name="admin_analytics")
router.message.filter(AdminFilter(PERMISSION_ANALYTICS))
router.callback_query.filter(AdminFilter(PERMISSION_ANALYTICS))


def _conversion_percent(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{(value / total) * 100:.0f}%"


def _render_product_funnel(items: tuple[ProductFunnelSnapshot, ...]) -> list[str]:
    lines = ["Топ продуктов по выручке:"]
    if not items:
        lines.append("• Пока нет данных по продуктам.")
        return lines
    for item in items[:5]:
        paid_percent = _conversion_percent(item.paid_users, item.buy_viewed_users)
        invite_percent = _conversion_percent(item.invite_issued_users, item.paid_users)
        lines.append(
            "• "
            f"{item.channel_title}: buy {item.buy_viewed_users} "
            f"→ invoice {item.invoice_created_users} "
            f"→ paid {item.paid_users} ({paid_percent})"
        )
        lines.append(
            "  "
            f"invite {item.invite_issued_users} ({invite_percent}) • "
            f"repeat {item.repeat_purchase_users} • revenue {item.revenue_total}"
        )
    return lines


def _render_analytics(snapshot: AnalyticsSnapshot) -> str:
    buy_percent = _conversion_percent(
        snapshot.conversion_buy_viewed,
        snapshot.conversion_started,
    )
    product_percent = _conversion_percent(
        snapshot.conversion_product_selected,
        snapshot.conversion_buy_viewed,
    )
    detail_percent = _conversion_percent(
        snapshot.conversion_tariff_opened,
        snapshot.conversion_buy_viewed,
    )
    invoice_percent = _conversion_percent(
        snapshot.conversion_invoice_created,
        snapshot.conversion_buy_viewed,
    )
    paid_percent = _conversion_percent(
        snapshot.conversion_paid,
        snapshot.conversion_buy_viewed,
    )
    invite_percent = _conversion_percent(
        snapshot.conversion_invite_issued,
        snapshot.conversion_paid,
    )
    lines = [
        "Аналитика",
        "",
        "Пользователи и подписки:",
        f"• Всего пользователей: {snapshot.total_users}",
        f"• Активных подписок: {snapshot.active_subscriptions}",
        f"• Истекших подписок: {snapshot.expired_users}",
        f"• Ни разу не покупали: {snapshot.never_paid_users}",
        f"• Заблокированных: {snapshot.blocked_users}",
        "",
        "Выручка:",
        f"• Сегодня: {snapshot.revenue_today}",
        f"• 7 дней: {snapshot.revenue_7_days}",
        f"• 30 дней: {snapshot.revenue_30_days}",
        f"• Всё время: {snapshot.revenue_total}",
        "",
        "Платежи:",
        f"• Stars: {snapshot.stars_payments}",
        f"• Crypto: {snapshot.crypto_payments}",
        "",
        "Воронка:",
        f"• /start: {snapshot.conversion_started}",
        f"• Buy screen: {snapshot.conversion_buy_viewed} ({buy_percent})",
        f"• Product selected: {snapshot.conversion_product_selected} ({product_percent})",
        f"• Tariff opened: {snapshot.conversion_tariff_opened} ({detail_percent})",
        f"• Invoice created: {snapshot.conversion_invoice_created} ({invoice_percent})",
        f"• Paid: {snapshot.conversion_paid} ({paid_percent})",
        f"• Invite issued: {snapshot.conversion_invite_issued} ({invite_percent})",
        f"• Repeat purchases: {snapshot.repeat_purchase_users}",
        "",
    ]
    lines.extend(_render_product_funnel(snapshot.product_funnel))
    return "\n".join(lines)


@router.callback_query(F.data == "menu:admin:analytics")
async def analytics_dashboard(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()

    snapshot = await build_analytics_snapshot(session)
    await edit_or_answer(
        callback,
        text=_render_analytics(snapshot),
        reply_markup=admin_analytics_keyboard(),
    )