from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_broadcasts import (
    admin_broadcast_detail_keyboard,
    admin_broadcast_filter_keyboard,
    admin_broadcast_item_filter_keyboard,
    admin_broadcast_preview_keyboard,
    admin_broadcasts_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminBroadcastForm
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.services.broadcasts import (
    BroadcastCampaignSnapshot,
    BroadcastValidationError,
    get_broadcast_campaign_snapshot,
    list_broadcast_campaign_snapshots,
    queue_broadcast_campaign,
    select_broadcast_recipients,
)
from app.services.users import list_active_channels, list_active_tariffs
from app.utils.datetime import format_datetime

router = Router(name="admin_broadcasts")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())



def _callback_campaign_id(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", 1)[-1])
    except ValueError:
        return None



def _render_broadcasts_overview(
    campaigns: list[BroadcastCampaignSnapshot],
    *,
    timezone: str,
) -> str:
    lines = [
        "Рассылки",
        "",
        "Создавайте кампании из админки, отправляйте их в очередь и следите за результатами.",
        "",
    ]
    if not campaigns:
        lines.append("Пока нет ни одной кампании. Создайте первую рассылку.")
        return "\n".join(lines)

    for snapshot in campaigns:
        lines.append(
            f"#{snapshot.campaign.id} • {snapshot.filter_label} • {snapshot.campaign.status}"
        )
        lines.append(
            f"Отправлено: {snapshot.campaign.sent_count} • "
            f"Ошибок: {snapshot.campaign.failed_count} • "
            f"Заблокировали бота: {snapshot.blocked_count}"
        )
        lines.append(f"Осталось: {snapshot.remaining_count} из {snapshot.campaign.total_targets}")
        if snapshot.campaign.started_at is not None:
            lines.append(
                f"Старт: {format_datetime(snapshot.campaign.started_at, timezone)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()



def _render_campaign_detail(snapshot: BroadcastCampaignSnapshot, *, timezone: str) -> str:
    campaign = snapshot.campaign
    lines = [
        f"Рассылка #{campaign.id}",
        "",
        f"Статус: {campaign.status}",
        f"Фильтр: {snapshot.filter_label}",
        f"Всего получателей: {campaign.total_targets}",
        f"Отправлено: {campaign.sent_count}",
        f"Ошибок: {campaign.failed_count}",
        f"Заблокировали бота: {snapshot.blocked_count}",
        f"Осталось: {snapshot.remaining_count}",
    ]
    if campaign.started_at is not None:
        lines.append(f"Старт: {format_datetime(campaign.started_at, timezone)}")
    if campaign.finished_at is not None:
        lines.append(f"Завершена: {format_datetime(campaign.finished_at, timezone)}")

    lines.extend(["", "Текст:", "", escape(campaign.content)])

    if snapshot.recent_failures:
        lines.extend(["", "Последние ошибки:"])
        for user_id, telegram_id, error_message in snapshot.recent_failures:
            error_text = escape(error_message or "ошибка без текста")
            lines.append(f"• user #{user_id} / Telegram {telegram_id}: {error_text}")

    return "\n".join(lines)



def _render_broadcast_preview(*, filter_label: str, total_targets: int, content: str) -> str:
    return "\n".join(
        [
            "Preview рассылки",
            "",
            f"Фильтр: {filter_label}",
            f"Получателей: {total_targets}",
            "Заблокированные пользователи исключаются автоматически.",
            "",
            "Текст:",
            "",
            escape(content),
            "",
            "После подтверждения кампания уйдёт в очередь фоновой отправки.",
        ]
    )


@router.callback_query(F.data == "menu:admin:broadcasts")
async def broadcasts_index(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
    settings=None,
) -> None:
    if state is not None:
        await state.clear()

    campaigns = await list_broadcast_campaign_snapshots(session, limit=10)
    timezone = getattr(settings, "timezone", "UTC")
    await edit_or_answer(
        callback,
        text=_render_broadcasts_overview(campaigns, timezone=timezone),
        reply_markup=admin_broadcasts_keyboard(campaigns),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:create")
async def start_broadcast_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback,
        text=(
            "Создание рассылки\n\n"
            "Сначала выберите фильтр получателей. "
            "После этого бот попросит прислать текст сообщения."
        ),
        reply_markup=admin_broadcast_filter_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:pick-filter:tariff")
async def pick_broadcast_tariff_filter(callback: CallbackQuery, session: AsyncSession) -> None:
    tariffs = await list_active_tariffs(session)
    await edit_or_answer(
        callback,
        text="Выберите тариф для фильтра рассылки.",
        reply_markup=admin_broadcast_item_filter_keyboard(tariffs, kind="tariff"),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:pick-filter:channel")
async def pick_broadcast_channel_filter(callback: CallbackQuery, session: AsyncSession) -> None:
    channels = await list_active_channels(session)
    await edit_or_answer(
        callback,
        text="Выберите канал для фильтра рассылки.",
        reply_markup=admin_broadcast_item_filter_keyboard(channels, kind="channel"),
    )


@router.callback_query(F.data.startswith("menu:admin:broadcasts:filter:"))
async def select_broadcast_filter(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None:
        await callback.answer()
        return

    filter_name = callback.data.removeprefix("menu:admin:broadcasts:filter:")
    await state.clear()
    await state.set_state(AdminBroadcastForm.waiting_for_content)
    await state.update_data(broadcast_filter=filter_name)
    await edit_or_answer(
        callback,
        text=(
            "Текст рассылки\n\n"
            "Отправьте одним сообщением текст, который нужно разослать выбранной аудитории."
        ),
        reply_markup=admin_broadcast_filter_keyboard(),
    )


@router.message(AdminBroadcastForm.waiting_for_content)
async def receive_broadcast_content(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.text is None or not message.text.strip():
        await message.answer("Нужен непустой текст рассылки.")
        return

    data = await state.get_data()
    filter_name = data.get("broadcast_filter")
    if not isinstance(filter_name, str) or not filter_name:
        await state.clear()
        await message.answer("Контекст создания рассылки потерян. Откройте раздел заново.")
        return

    try:
        preview = await select_broadcast_recipients(session, filter_name=filter_name)
    except BroadcastValidationError as exc:
        await message.answer(str(exc))
        return

    if not preview.user_ids:
        await message.answer(
            "По выбранному фильтру сейчас нет получателей. Смените фильтр и попробуйте снова."
        )
        return

    await state.update_data(
        broadcast_content=message.text.strip(),
        broadcast_filter_label=preview.filter_label,
        broadcast_total_targets=preview.total_targets,
    )
    await message.answer(
        _render_broadcast_preview(
            filter_label=preview.filter_label,
            total_targets=preview.total_targets,
            content=message.text.strip(),
        ),
        reply_markup=admin_broadcast_preview_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:confirm")
async def confirm_broadcast_creation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings,
) -> None:
    data = await state.get_data()
    filter_name = data.get("broadcast_filter")
    content = data.get("broadcast_content")
    if not isinstance(filter_name, str) or not isinstance(content, str):
        await state.clear()
        await callback.answer(
            "Контекст рассылки потерян. Создайте кампанию заново.",
            show_alert=True,
        )
        return

    actor_user_id = None
    if callback.from_user is not None:
        actor = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        actor_user_id = actor.id if actor is not None else None

    try:
        campaign = await queue_broadcast_campaign(
            session,
            created_by_user_id=actor_user_id,
            filter_name=filter_name,
            content=content,
        )
        await write_audit_log(
            session,
            action="broadcast_created",
            actor_user_id=actor_user_id,
            payload={
                "campaign_id": campaign.id,
                "filter_name": filter_name,
                "total_targets": campaign.total_targets,
            },
        )
        await session.commit()
    except BroadcastValidationError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    snapshot = await get_broadcast_campaign_snapshot(session, campaign.id)
    if snapshot is None:
        await callback.answer("Не удалось загрузить созданную кампанию.", show_alert=True)
        return

    await edit_or_answer(
        callback,
        text=_render_campaign_detail(snapshot, timezone=settings.timezone),
        reply_markup=admin_broadcast_detail_keyboard(campaign.id),
    )


@router.callback_query(F.data.startswith("menu:admin:broadcasts:view:"))
async def broadcast_detail(callback: CallbackQuery, session: AsyncSession, settings) -> None:
    campaign_id = _callback_campaign_id(callback.data)
    if campaign_id is None:
        await callback.answer()
        return

    snapshot = await get_broadcast_campaign_snapshot(session, campaign_id)
    if snapshot is None:
        await callback.answer("Кампания не найдена.", show_alert=True)
        return

    await edit_or_answer(
        callback,
        text=_render_campaign_detail(snapshot, timezone=settings.timezone),
        reply_markup=admin_broadcast_detail_keyboard(campaign_id),
    )