# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin import (
    admin_channel_picker_keyboard,
    admin_form_keyboard,
    admin_tariff_detail_keyboard,
    admin_tariffs_keyboard,
)
from app.bot.routers.common import edit_or_answer
from app.bot.states.admin import AdminTariffForm
from app.db.models import Channel, Tariff
from app.db.repositories.channels import ChannelRepository
from app.db.repositories.tariffs import TariffRepository
from app.services.admin_roles import PERMISSION_TARIFFS
from app.services.tariffs import (
    TariffValidationError,
    effective_crypto_asset,
    effective_crypto_price,
    ensure_channel_can_host_tariff,
    parse_positive_int,
    tariff_badge_label,
    tariff_duration_label,
    validate_optional_badge,
    validate_tariff_name,
    validate_tariff_payload,
)

router = Router(name="admin_tariffs")
router.message.filter(AdminFilter(PERMISSION_TARIFFS))
router.callback_query.filter(AdminFilter(PERMISSION_TARIFFS))


def _callback_entity_id(data: str | None) -> int | None:
    if data is None:
        return None
    try:
        return int(data.rsplit(":", 1)[-1])
    except ValueError:
        return None


def _tariff_status(tariff: Tariff) -> str:
    if tariff.archived_at is not None:
        return "архив"
    if tariff.is_active:
        return "активен"
    return "выключен"


def _render_tariffs_overview(tariffs: list[Tariff]) -> str:
    lines = [
        "Тарифы",
        "",
        "Здесь создаются предложения, которые увидит пользователь перед оплатой.",
        "",
    ]
    if not tariffs:
        lines.append("Пока нет ни одного тарифа. Сначала добавьте канал, затем создайте тариф.")
        return "\n".join(lines)

    lines.append(f"Всего тарифов: {len(tariffs)}")
    lines.append("")
    for tariff in tariffs:
        status_icon = "📦" if tariff.archived_at else ("✅" if tariff.is_active else "⏸")
        badge = tariff_badge_label(tariff)
        prefix = f"[{escape(badge)}] " if badge else ""
        lines.append(f"{status_icon} {prefix}{escape(tariff.name)}")
        lines.append(
            f"{tariff.price_stars} Stars • {tariff_duration_label(tariff)} • канал {escape(tariff.channel.title)}"
        )
        lines.append(f"Статус: {_tariff_status(tariff)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_tariff_detail(tariff: Tariff) -> str:
    archived = ""
    if tariff.archived_at is not None:
        archived_at = tariff.archived_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        archived = f"\nАрхивирован: {archived_at}"

    badge = tariff_badge_label(tariff) or "—"
    crypto_price = effective_crypto_price(tariff)
    crypto_asset = effective_crypto_asset(tariff, ["USDT"]) or "—"
    crypto_line = "—" if crypto_price is None else f"{crypto_price} {crypto_asset}"
    description = escape(tariff.description) if tariff.description else "—"

    return (
        f"Тариф #{tariff.id}\n\n"
        f"Название: {escape(tariff.name)}\n"
        f"Бейдж: {escape(badge)}\n"
        f"Описание: {description}\n"
        f"Цена: {tariff.price_stars} Stars\n"
        f"Crypto Pay: {crypto_line}\n"
        f"Длительность: {tariff_duration_label(tariff)}\n"
        f"Trial: {'да' if tariff.is_trial else 'нет'}\n"
        f"Lifetime: {'да' if tariff.is_lifetime else 'нет'}\n"
        f"Канал: {escape(tariff.channel.title)}\n"
        f"Сортировка: {tariff.sort_order}\n"
        f"Статус: {_tariff_status(tariff)}"
        f"{archived}"
    )


def _render_user_preview(tariff: Tariff) -> str:
    badge = tariff_badge_label(tariff)
    badge_line = f"🏷 {escape(badge)}\n" if badge else ""
    description_line = f"📝 {escape(tariff.description)}\n" if tariff.description else ""
    crypto_price = effective_crypto_price(tariff)
    crypto_asset = effective_crypto_asset(tariff, ["USDT"]) or "—"
    crypto_line = ""
    if crypto_price is not None:
        crypto_line = f"₿ Crypto Pay: {crypto_price} {crypto_asset}\n"
    return (
        "Превью как пользователь\n\n"
        f"💎 {escape(tariff.name)}\n"
        f"{badge_line}"
        f"⏳ Срок: {tariff_duration_label(tariff)}\n"
        f"⭐ Цена: {tariff.price_stars} Stars\n"
        f"📣 Канал: {escape(tariff.channel.title)}\n"
        f"{description_line}"
        f"{crypto_line}"
    ).rstrip()


def _render_channel_picker_prompt(channels: list[Channel]) -> str:
    if not channels:
        return (
            "Нет каналов, которые можно использовать в тарифах.\n\n"
            "Нужен активный канал, где у бота есть право приглашать и удалять пользователей."
        )
    return "Выберите канал для тарифа."


async def _show_tariff_detail(target: Message | CallbackQuery, tariff: Tariff) -> None:
    await edit_or_answer(
        target,
        text=_render_tariff_detail(tariff),
        reply_markup=admin_tariff_detail_keyboard(
            tariff.id,
            is_active=tariff.is_active,
            is_archived=tariff.archived_at is not None,
            is_trial=tariff.is_trial,
            is_lifetime=tariff.is_lifetime,
        ),
    )


@router.callback_query(F.data == "menu:admin:tariffs")
async def tariffs_index(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state is not None:
        await state.clear()

    tariffs = await TariffRepository(session).list_all()
    await edit_or_answer(
        callback,
        text=_render_tariffs_overview(tariffs),
        reply_markup=admin_tariffs_keyboard(tariffs),
    )


@router.callback_query(F.data == "menu:admin:tariffs:create")
async def start_tariff_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_name)
    await state.update_data(tariff_action="create")
    await edit_or_answer(
        callback,
        text="Создание тарифа\n\nОтправьте название тарифа.",
        reply_markup=admin_form_keyboard(back_callback="menu:admin:tariffs"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:view:"))
async def tariff_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await _show_tariff_detail(callback, tariff)


@router.callback_query(F.data.startswith("menu:admin:tariffs:preview:"))
async def tariff_preview(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await edit_or_answer(
        callback,
        text=_render_user_preview(tariff),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:tariffs:view:{tariff.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:rename:"))
async def start_tariff_rename(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_new_name)
    await state.update_data(tariff_action="rename", tariff_id=tariff.id)
    await edit_or_answer(
        callback,
        text=(
            f"Изменение названия тарифа #{tariff.id}\n\n"
            f"Текущее название: {escape(tariff.name)}\n\n"
            "Отправьте новое название."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:tariffs:view:{tariff.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:price:"))
async def start_tariff_price_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_new_price)
    await state.update_data(tariff_action="price", tariff_id=tariff.id)
    await edit_or_answer(
        callback,
        text=(
            f"Изменение цены тарифа #{tariff.id}\n\n"
            f"Текущая цена: {tariff.price_stars} Stars\n\n"
            "Отправьте новую цену целым числом."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:tariffs:view:{tariff.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:days:"))
async def start_tariff_days_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_new_days)
    await state.update_data(tariff_action="days", tariff_id=tariff.id)
    await edit_or_answer(
        callback,
        text=(
            f"Изменение длительности тарифа #{tariff.id}\n\n"
            f"Текущая длительность: {tariff.duration_days} дн.\n\n"
            "Отправьте новое количество дней."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:tariffs:view:{tariff.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:sort:"))
async def start_tariff_sort_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_new_sort)
    await state.update_data(tariff_action="sort", tariff_id=tariff.id)
    await edit_or_answer(
        callback,
        text=(
            f"Изменение сортировки тарифа #{tariff.id}\n\n"
            f"Текущая сортировка: {tariff.sort_order}\n\n"
            "Отправьте новый порядок показа целым числом."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:tariffs:view:{tariff.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:badge:"))
async def start_tariff_badge_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_new_badge)
    await state.update_data(tariff_action="badge", tariff_id=tariff.id)
    current_badge = tariff_badge_label(tariff) or "—"
    await edit_or_answer(
        callback,
        text=(
            f"Изменение бейджа тарифа #{tariff.id}\n\n"
            f"Текущий бейдж: {escape(current_badge)}\n\n"
            "Отправьте новый бейдж или пустое сообщение, чтобы убрать его."
        ),
        reply_markup=admin_form_keyboard(back_callback=f"menu:admin:tariffs:view:{tariff.id}"),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:channel:"))
async def start_tariff_channel_edit(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    tariff = await TariffRepository(session).get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    channels = await ChannelRepository(session).list_available_for_tariffs()
    await state.clear()
    await state.set_state(AdminTariffForm.waiting_for_new_channel)
    await state.update_data(tariff_action="change_channel", tariff_id=tariff.id)
    await edit_or_answer(
        callback,
        text=_render_channel_picker_prompt(channels),
        reply_markup=admin_channel_picker_keyboard(
            channels,
            back_callback=f"menu:admin:tariffs:view:{tariff.id}",
        ),
    )


@router.callback_query(F.data.startswith("menu:admin:tariffs:trial:"))
async def toggle_trial_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return
    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return
    if tariff.archived_at is not None:
        await callback.answer("Архивный тариф нельзя редактировать.")
        return

    tariff.is_trial = not tariff.is_trial
    if tariff.is_trial:
        tariff.is_lifetime = False
    await session.commit()
    await _show_tariff_detail(callback, tariff)


@router.callback_query(F.data.startswith("menu:admin:tariffs:lifetime:"))
async def toggle_lifetime_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return
    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return
    if tariff.archived_at is not None:
        await callback.answer("Архивный тариф нельзя редактировать.")
        return

    tariff.is_lifetime = not tariff.is_lifetime
    if tariff.is_lifetime:
        tariff.is_trial = False
    await session.commit()
    await _show_tariff_detail(callback, tariff)


@router.callback_query(F.data.startswith("menu:admin:tariffs:toggle:"))
async def toggle_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    if tariff.archived_at is not None:
        await callback.answer("Архивный тариф нельзя снова включить.")
        return

    if not tariff.is_active:
        try:
            ensure_channel_can_host_tariff(tariff.channel)
        except TariffValidationError as exc:
            await callback.answer(str(exc))
            return

    await repository.set_active(tariff, is_active=not tariff.is_active)
    await session.commit()
    await _show_tariff_detail(callback, tariff)


@router.callback_query(F.data.startswith("menu:admin:tariffs:archive:"))
async def archive_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    if tariff.archived_at is None:
        await repository.archive(tariff, archived_at=datetime.now(UTC))
        await session.commit()

    await _show_tariff_detail(callback, tariff)


@router.callback_query(F.data.startswith("menu:admin:tariffs:unarchive:"))
async def unarchive_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = _callback_entity_id(callback.data)
    if tariff_id is None:
        await callback.answer()
        return

    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff_id)
    if tariff is None:
        await callback.answer("Тариф не найден.")
        return

    await repository.unarchive(tariff)
    await session.commit()
    await _show_tariff_detail(callback, tariff)


@router.callback_query(F.data.startswith("menu:admin:tariffs:pick-channel:"))
async def pick_tariff_channel(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    channel_id = _callback_entity_id(callback.data)
    if channel_id is None:
        await callback.answer()
        return

    data = await state.get_data()
    action = data.get("tariff_action")
    channel = await ChannelRepository(session).get_by_id(channel_id)

    try:
        if action == "create":
            draft = validate_tariff_payload(
                name=str(data.get("name", "")),
                price_stars=str(data.get("price_stars", "")),
                duration_days=str(data.get("duration_days", "")),
                channel=channel,
            )
            created_tariff = await TariffRepository(session).create(draft)
            await session.commit()
            await state.clear()
            tariff = await TariffRepository(session).get_by_id(created_tariff.id)
            if tariff is None:
                await callback.answer("Не удалось загрузить созданный тариф.")
                return
            await edit_or_answer(
                callback,
                text="Тариф создан.\n\n" + _render_tariff_detail(tariff),
                reply_markup=admin_tariff_detail_keyboard(
                    tariff.id,
                    is_active=tariff.is_active,
                    is_archived=tariff.archived_at is not None,
                    is_trial=tariff.is_trial,
                    is_lifetime=tariff.is_lifetime,
                ),
            )
            return

        if action == "change_channel":
            tariff_id = data.get("tariff_id")
            if not isinstance(tariff_id, int):
                raise TariffValidationError("Не удалось определить тариф.")
            repository = TariffRepository(session)
            tariff = await repository.get_by_id(tariff_id)
            if tariff is None:
                raise TariffValidationError("Тариф не найден.")
            if tariff.archived_at is not None:
                raise TariffValidationError("Нельзя менять архивный тариф.")

            validated_channel = ensure_channel_can_host_tariff(channel)
            tariff.channel_id = validated_channel.id
            await session.commit()
            await state.clear()
            refreshed = await repository.get_by_id(tariff.id)
            if refreshed is None:
                await callback.answer("Тариф не найден после обновления.")
                return
            await _show_tariff_detail(callback, refreshed)
            return
    except TariffValidationError as exc:
        await callback.answer(str(exc))
        return

    await state.clear()
    await callback.answer("Форма выбора канала больше не активна.")


@router.message(AdminTariffForm.waiting_for_name)
async def receive_tariff_name(message: Message, state: FSMContext) -> None:
    try:
        name = validate_tariff_name(message.text or "")
    except TariffValidationError as exc:
        await message.answer(f"{exc}\n\nПопробуйте ещё раз.")
        return

    await state.update_data(tariff_action="create", name=name)
    await state.set_state(AdminTariffForm.waiting_for_price)
    await message.answer("Отправьте цену в Telegram Stars целым числом.")


@router.message(AdminTariffForm.waiting_for_price)
async def receive_tariff_price(message: Message, state: FSMContext) -> None:
    try:
        price = parse_positive_int(message.text or "", "цена")
    except TariffValidationError as exc:
        await message.answer(f"{exc}\n\nПопробуйте ещё раз.")
        return

    await state.update_data(price_stars=price)
    await state.set_state(AdminTariffForm.waiting_for_days)
    await message.answer("Отправьте длительность подписки в днях.")


@router.message(AdminTariffForm.waiting_for_days)
async def receive_tariff_days(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        duration_days = parse_positive_int(message.text or "", "длительность")
    except TariffValidationError as exc:
        await message.answer(f"{exc}\n\nПопробуйте ещё раз.")
        return

    channels = await ChannelRepository(session).list_available_for_tariffs()
    if not channels:
        await state.clear()
        await message.answer(
            "Нет активных каналов с нужными правами. Сначала добавьте и настройте канал."
        )
        return

    await state.update_data(duration_days=duration_days)
    await state.set_state(AdminTariffForm.waiting_for_channel)
    await message.answer(
        _render_channel_picker_prompt(channels),
        reply_markup=admin_channel_picker_keyboard(
            channels,
            back_callback="menu:admin:tariffs",
        ),
    )


async def _update_tariff_field_from_message(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    field_name: str,
    parser,
) -> None:
    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    if not isinstance(tariff_id, int):
        await state.clear()
        await message.answer("Не удалось определить тариф. Откройте карточку заново.")
        return

    repository = TariffRepository(session)
    tariff = await repository.get_by_id(tariff_id)
    if tariff is None:
        await state.clear()
        await message.answer("Тариф не найден.")
        return
    if tariff.archived_at is not None:
        await state.clear()
        await message.answer("Архивный тариф больше нельзя редактировать.")
        return

    try:
        setattr(tariff, field_name, parser(message.text or ""))
    except TariffValidationError as exc:
        await message.answer(f"{exc}\n\nПопробуйте ещё раз.")
        return

    await session.commit()
    await state.clear()
    await message.answer(
        "Тариф обновлён.\n\n" + _render_tariff_detail(tariff),
        reply_markup=admin_tariff_detail_keyboard(
            tariff.id,
            is_active=tariff.is_active,
            is_archived=tariff.archived_at is not None,
            is_trial=tariff.is_trial,
            is_lifetime=tariff.is_lifetime,
        ),
    )


@router.message(AdminTariffForm.waiting_for_new_name)
async def receive_new_tariff_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _update_tariff_field_from_message(
        message=message,
        state=state,
        session=session,
        field_name="name",
        parser=validate_tariff_name,
    )


@router.message(AdminTariffForm.waiting_for_new_price)
async def receive_new_tariff_price(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _update_tariff_field_from_message(
        message=message,
        state=state,
        session=session,
        field_name="price_stars",
        parser=lambda raw: parse_positive_int(raw, "цена"),
    )


@router.message(AdminTariffForm.waiting_for_new_days)
async def receive_new_tariff_days(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _update_tariff_field_from_message(
        message=message,
        state=state,
        session=session,
        field_name="duration_days",
        parser=lambda raw: parse_positive_int(raw, "длительность"),
    )


@router.message(AdminTariffForm.waiting_for_new_sort)
async def receive_new_tariff_sort(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _update_tariff_field_from_message(
        message=message,
        state=state,
        session=session,
        field_name="sort_order",
        parser=lambda raw: parse_positive_int(raw, "сортировка"),
    )


@router.message(AdminTariffForm.waiting_for_new_badge)
async def receive_new_tariff_badge(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _update_tariff_field_from_message(
        message=message,
        state=state,
        session=session,
        field_name="badge",
        parser=validate_optional_badge,
    )


