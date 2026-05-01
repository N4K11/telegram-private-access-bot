
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_broadcasts import (
    admin_broadcast_content_keyboard,
    admin_broadcast_detail_keyboard,
    admin_broadcast_filter_keyboard,
    admin_broadcast_item_filter_keyboard,
    admin_broadcast_preview_keyboard,
    admin_broadcast_template_list_keyboard,
    admin_broadcasts_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminBroadcastForm
from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.admin_roles import PERMISSION_BROADCASTS
from app.services.audit import write_audit_log
from app.services.broadcasts import (
    BroadcastCampaignSnapshot,
    BroadcastValidationError,
    get_broadcast_campaign_snapshot,
    get_broadcast_template,
    list_broadcast_campaign_snapshots,
    list_broadcast_templates,
    queue_broadcast_campaign,
    save_broadcast_template,
    select_broadcast_recipients,
)
from app.services.users import filter_label, list_active_channels, list_active_tariffs
from app.utils.datetime import format_datetime

router = Router(name="admin_broadcasts")
router.message.filter(AdminFilter(PERMISSION_BROADCASTS))
router.callback_query.filter(AdminFilter(PERMISSION_BROADCASTS))


def _callback_campaign_id(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", 1)[-1])
    except ValueError:
        return None


def _callback_template_key(data: str | None) -> str | None:
    if not data or not data.startswith("menu:admin:broadcasts:template:"):
        return None
    return data.removeprefix("menu:admin:broadcasts:template:")


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
            f"Отправлено: {snapshot.campaign.sent_count} • Ошибок: {snapshot.campaign.failed_count}"
        )
        lines.append(
            f"Rate limited: {snapshot.rate_limited_count} • "
            f"Заблокировали бота: {snapshot.blocked_count}"
        )
        lines.append(f"Осталось: {snapshot.remaining_count} из {snapshot.campaign.total_targets}")
        if snapshot.campaign.started_at is not None:
            lines.append(f"Старт: {format_datetime(snapshot.campaign.started_at, timezone)}")
        if snapshot.campaign.finished_at is not None:
            lines.append(
                f"Завершена: {format_datetime(snapshot.campaign.finished_at, timezone)}"
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
        f"Rate limited: {snapshot.rate_limited_count}",
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
        for user_id, telegram_id, status, error_message in snapshot.recent_failures:
            error_text = escape(error_message or "ошибка без текста")
            lines.append(
                f"• user #{user_id} / Telegram {telegram_id} / {status}: {error_text}"
            )

    return "\n".join(lines)


def _render_broadcast_preview(
    *,
    filter_label_value: str,
    total_targets: int,
    content: str,
    sample_labels: list[str],
    template_title: str | None = None,
) -> str:
    lines = [
        "Preview рассылки",
        "",
        f"Фильтр: {filter_label_value}",
        f"Получателей: {total_targets}",
        "Заблокированные пользователи исключаются автоматически.",
    ]
    if template_title:
        lines.append(f"Шаблон: {template_title}")
    if sample_labels:
        lines.extend(["", "Первые получатели:"])
        for label in sample_labels:
            lines.append(f"• {escape(label)}")
    lines.extend(
        [
            "",
            "Текст:",
            "",
            escape(content),
            "",
            "После подтверждения кампания уйдёт в очередь фоновой отправки.",
        ]
    )
    return "\n".join(lines)


def _render_broadcast_content_entry(filter_name: str) -> str:
    return "\n".join(
        [
            "Текст рассылки",
            "",
            f"Фильтр: {filter_label(filter_name)}",
            "Отправьте одним сообщением текст для рассылки или выберите готовый шаблон.",
        ]
    )

@router.callback_query(F.data == "menu:admin:broadcasts")
async def broadcasts_index(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
    settings: Settings | None = None,
) -> None:
    if state is not None:
        await state.clear()

    campaigns = await list_broadcast_campaign_snapshots(session, limit=10)
    timezone = settings.timezone if settings is not None else "UTC"
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
            "Сначала выберите фильтр получателей. После этого бот предложит прислать текст "
            "или использовать сохранённый шаблон."
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
    await state.update_data(
        broadcast_filter=filter_name,
        broadcast_content=None,
        broadcast_template_title=None,
        broadcast_sample_labels=[],
    )
    await edit_or_answer(
        callback,
        text=_render_broadcast_content_entry(filter_name),
        reply_markup=admin_broadcast_content_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:content-entry")
async def broadcast_content_entry(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    filter_name = data.get("broadcast_filter")
    if not isinstance(filter_name, str) or not filter_name:
        await callback.answer("Сначала выберите фильтр рассылки.", show_alert=True)
        return
    await state.set_state(AdminBroadcastForm.waiting_for_content)
    await edit_or_answer(
        callback,
        text=_render_broadcast_content_entry(filter_name),
        reply_markup=admin_broadcast_content_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:templates")
async def browse_broadcast_templates(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    filter_name = data.get("broadcast_filter")
    if not isinstance(filter_name, str) or not filter_name:
        await callback.answer("Сначала выберите фильтр рассылки.", show_alert=True)
        return

    templates = await list_broadcast_templates(session, limit=20)
    if not templates:
        await callback.answer("Сохранённых шаблонов пока нет.", show_alert=True)
        return

    await edit_or_answer(
        callback,
        text="Выберите шаблон для предпросмотра.",
        reply_markup=admin_broadcast_template_list_keyboard(templates),
    )


@router.callback_query(F.data.startswith("menu:admin:broadcasts:template:"))
async def choose_broadcast_template(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    template_key = _callback_template_key(callback.data)
    if template_key is None:
        await callback.answer()
        return

    data = await state.get_data()
    filter_name = data.get("broadcast_filter")
    if not isinstance(filter_name, str) or not filter_name:
        await callback.answer("Сначала выберите фильтр рассылки.", show_alert=True)
        return

    template = await get_broadcast_template(session, key=template_key)
    if template is None:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return

    preview = await select_broadcast_recipients(session, filter_name=filter_name)
    sample_labels = [sample.label for sample in preview.samples]
    await state.set_state(AdminBroadcastForm.waiting_for_content)
    await state.update_data(
        broadcast_content=template.content,
        broadcast_filter_label=preview.filter_label,
        broadcast_total_targets=preview.total_targets,
        broadcast_sample_labels=sample_labels,
        broadcast_template_title=template.title,
    )
    await edit_or_answer(
        callback,
        text=_render_broadcast_preview(
            filter_label_value=preview.filter_label,
            total_targets=preview.total_targets,
            content=template.content,
            sample_labels=sample_labels,
            template_title=template.title,
        ),
        reply_markup=admin_broadcast_preview_keyboard(),
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

    normalized_content = message.text.strip()
    sample_labels = [sample.label for sample in preview.samples]
    await state.update_data(
        broadcast_content=normalized_content,
        broadcast_filter_label=preview.filter_label,
        broadcast_total_targets=preview.total_targets,
        broadcast_sample_labels=sample_labels,
        broadcast_template_title=None,
    )
    await message.answer(
        _render_broadcast_preview(
            filter_label_value=preview.filter_label,
            total_targets=preview.total_targets,
            content=normalized_content,
            sample_labels=sample_labels,
        ),
        reply_markup=admin_broadcast_preview_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:save-template")
async def prompt_save_broadcast_template(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    content = data.get("broadcast_content")
    if not isinstance(content, str) or not content.strip():
        await callback.answer("Сначала подготовьте preview рассылки.", show_alert=True)
        return

    await state.set_state(AdminBroadcastForm.waiting_for_template_name)
    await edit_or_answer(
        callback,
        text="Отправьте название шаблона одним сообщением.",
    )


@router.message(AdminBroadcastForm.waiting_for_template_name)
async def receive_broadcast_template_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.text is None or not message.text.strip():
        await message.answer("Нужно непустое название шаблона.")
        return

    data = await state.get_data()
    content = data.get("broadcast_content")
    filter_label_value = data.get("broadcast_filter_label")
    total_targets = data.get("broadcast_total_targets")
    sample_labels = data.get("broadcast_sample_labels") or []
    if not isinstance(content, str) or not isinstance(filter_label_value, str):
        await state.clear()
        await message.answer("Контекст preview потерян. Подготовьте рассылку заново.")
        return

    actor_user_id = None
    if message.from_user is not None:
        actor = await UserRepository(session).get_by_telegram_id(message.from_user.id)
        actor_user_id = actor.id if actor is not None else None

    try:
        template = await save_broadcast_template(
            session,
            title=message.text.strip(),
            content=content,
            updated_by_user_id=actor_user_id,
        )
        await session.commit()
    except BroadcastValidationError as exc:
        await session.rollback()
        await message.answer(str(exc))
        return

    await state.set_state(AdminBroadcastForm.waiting_for_content)
    await state.update_data(broadcast_template_title=template.title)
    total_value = int(total_targets or 0)
    sample_lines = [str(item) for item in sample_labels if isinstance(item, str)]
    await message.answer(
        "💾 Шаблон сохранён.\n\n"
        + _render_broadcast_preview(
            filter_label_value=filter_label_value,
            total_targets=total_value,
            content=content,
            sample_labels=sample_lines,
            template_title=template.title,
        ),
        reply_markup=admin_broadcast_preview_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:broadcasts:confirm")
async def confirm_broadcast_creation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    data = await state.get_data()
    filter_name = data.get("broadcast_filter")
    content = data.get("broadcast_content")
    template_title = data.get("broadcast_template_title")
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
                "template_title": template_title,
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
async def broadcast_detail(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
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



