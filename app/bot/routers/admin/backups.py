# ruff: noqa: E501
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.admin_backups import admin_backups_keyboard
from app.bot.routers.common import edit_or_answer
from app.db.repositories.users import UserRepository
from app.services.audit import write_audit_log
from app.services.backups import (
    RESTORE_INSTRUCTIONS,
    apply_backup_retention,
    create_backup_archive,
    list_backup_records,
    mark_backup_delivery,
    send_backup_to_message,
)
from app.utils.datetime import format_datetime

router = Router(name="admin_backups")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


async def _actor_user_id(session: AsyncSession, telegram_user_id: int | None) -> int | None:
    if telegram_user_id is None:
        return None
    user = await UserRepository(session).get_by_telegram_id(telegram_user_id)
    return user.id if user is not None else None


def _render_backups_overview(records, settings) -> str:
    enabled = "\u0434\u0430" if settings.backup_enabled else "\u043d\u0435\u0442"
    send_to_admin = "\u0434\u0430" if settings.backup_send_to_admin else "\u043d\u0435\u0442"
    lines = [
        "\u0411\u044d\u043a\u0430\u043f\u044b",
        "",
        f"\u0415\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u044b\u0439 backup: {enabled}",
        f"\u0412\u0440\u0435\u043c\u044f: {settings.backup_time} ({settings.timezone})",
        f"Retention: {settings.backup_retention_days} \u0434\u043d.",
        f"\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u0430\u0434\u043c\u0438\u043d\u0443: {send_to_admin}",
        f"\u041f\u0430\u043f\u043a\u0430: <code>{escape(settings.backup_directory)}</code>",
        "",
        "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 backup:",
    ]
    if not records:
        lines.append("\u0415\u0449\u0451 \u043d\u0435\u0442 \u043d\u0438 \u043e\u0434\u043d\u043e\u0433\u043e backup.")
        return "\n".join(lines)

    for record in records:
        lines.extend(
            [
                "",
                f"#{record.id} \u2022 <code>{escape(record.file_name)}</code>",
                f"\u0421\u0442\u0430\u0442\u0443\u0441: {record.status}",
                f"\u0420\u0430\u0437\u043c\u0435\u0440: {record.size_bytes or 0} bytes",
                f"\u0421\u043e\u0437\u0434\u0430\u043d: {format_datetime(record.created_at, settings.timezone)}",
            ]
        )
        if record.sent_to_admin_at is not None:
            lines.append(
                f"\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d: {format_datetime(record.sent_to_admin_at, settings.timezone)}"
            )
    return "\n".join(lines)


@router.callback_query(F.data == "menu:admin:backups")
async def backups_index(callback: CallbackQuery, session: AsyncSession, settings) -> None:
    records = await list_backup_records(session, limit=10)
    await edit_or_answer(
        callback,
        text=_render_backups_overview(records, settings),
        reply_markup=admin_backups_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:backups:restore")
async def backups_restore_help(callback: CallbackQuery) -> None:
    await edit_or_answer(
        callback,
        text="\u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f \u043f\u043e \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044e\n\n" + RESTORE_INSTRUCTIONS,
        reply_markup=admin_backups_keyboard(),
    )


@router.callback_query(F.data == "menu:admin:backups:create")
async def create_backup_now(callback: CallbackQuery, session: AsyncSession, settings) -> None:
    actor_user_id = await _actor_user_id(
        session,
        callback.from_user.id if callback.from_user is not None else None,
    )

    try:
        artifact = await create_backup_archive(
            session,
            backup_root=settings.backup_directory,
            label="manual",
        )
        await write_audit_log(
            session,
            action="backup_created_manual",
            actor_user_id=actor_user_id,
            payload={
                "backup_record_id": artifact.record.id,
                "file_name": artifact.file_name,
                "size_bytes": artifact.size_bytes,
            },
        )
        await apply_backup_retention(
            session,
            backup_root=settings.backup_directory,
            retention_days=settings.backup_retention_days,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await callback.answer("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c backup.", show_alert=True)
        return

    if callback.message is None:
        await callback.answer("Backup created, but source message is unavailable.", show_alert=True)
        return

    delivered = False
    try:
        await send_backup_to_message(callback.message, artifact.record)
        delivered = True
    except Exception:
        delivered = False

    try:
        await mark_backup_delivery(session, artifact.record, delivered=delivered)
        await session.commit()
    except Exception:
        await session.rollback()

    records = await list_backup_records(session, limit=10)
    await edit_or_answer(
        callback,
        text=_render_backups_overview(records, settings),
        reply_markup=admin_backups_keyboard(),
    )