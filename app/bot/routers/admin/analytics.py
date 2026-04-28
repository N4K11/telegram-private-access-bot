from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_users import admin_analytics_keyboard
from app.bot.routers.common import edit_or_answer
from app.services.analytics import AnalyticsSnapshot, build_analytics_snapshot

router = Router(name="admin_analytics")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())



def _conversion_percent(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{(value / total) * 100:.0f}%"



def _render_analytics(snapshot: AnalyticsSnapshot) -> str:
    invoice_percent = _conversion_percent(
        snapshot.conversion_invoice_created,
        snapshot.conversion_started,
    )
    paid_percent = _conversion_percent(
        snapshot.conversion_paid,
        snapshot.conversion_started,
    )
    return "\n".join(
        [
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
            "Конверсия:",
            f"• /start: {snapshot.conversion_started}",
            (
                "• Инвойс создан: "
                f"{snapshot.conversion_invoice_created} ({invoice_percent})"
            ),
            f"• Оплачено: {snapshot.conversion_paid} ({paid_percent})",
        ]
    )


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