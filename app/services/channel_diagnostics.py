from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

from aiogram import Bot

from app.db.models import Channel
from app.utils.encoding import safe_ui_text


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    label: str
    ok: bool
    details: str


@dataclass(frozen=True, slots=True)
class ChannelDiagnosticResult:
    channel_id: int
    title: str
    telegram_chat_id: int
    username: str | None
    is_active: bool
    checks: tuple[DiagnosticCheck, ...]
    recommendations: tuple[str, ...] = ()

    @property
    def overall_ok(self) -> bool:
        return all(check.ok for check in self.checks)


@dataclass(frozen=True, slots=True)
class ChannelDiagnosticsReport:
    bot_username: str | None
    get_me_error: str | None
    results: tuple[ChannelDiagnosticResult, ...]

    @property
    def overall_ok(self) -> bool:
        return self.get_me_error is None and all(result.overall_ok for result in self.results)


async def build_channel_diagnostics_report(
    bot: Bot,
    channels: Sequence[Channel],
) -> ChannelDiagnosticsReport:
    bot_id: int | None = None
    bot_username: str | None = None
    get_me_error: str | None = None

    try:
        me = await bot.get_me()
        bot_id = getattr(me, "id", None)
        bot_username = getattr(me, "username", None)
    except Exception as exc:
        get_me_error = _readable_error(exc)

    results = [
        await _diagnose_channel(bot, channel, bot_id=bot_id)
        for channel in channels
    ]
    return ChannelDiagnosticsReport(
        bot_username=bot_username,
        get_me_error=get_me_error,
        results=tuple(results),
    )


async def _diagnose_channel(
    bot: Bot,
    channel: Channel,
    *,
    bot_id: int | None,
) -> ChannelDiagnosticResult:
    title = safe_ui_text(channel.title, f"Канал #{channel.id}")
    checks: list[DiagnosticCheck] = [
        DiagnosticCheck(
            label="Канал настроен",
            ok=True,
            details=f"<code>{channel.telegram_chat_id}</code>",
        )
    ]
    recommendations: list[str] = []

    if bot_id is None:
        checks.append(
            DiagnosticCheck(
                label="Live-проверка",
                ok=False,
                details="Пропущена: getMe недоступен.",
            )
        )
        recommendations.extend(
            [
                "Проверьте BOT_TOKEN и доступность Telegram API.",
                "Повторите диагностику после восстановления соединения.",
            ]
        )
        return ChannelDiagnosticResult(
            channel_id=channel.id,
            title=title,
            telegram_chat_id=channel.telegram_chat_id,
            username=channel.username,
            is_active=channel.is_active,
            checks=tuple(checks),
            recommendations=tuple(recommendations),
        )

    try:
        chat = await bot.get_chat(channel.telegram_chat_id)
    except Exception as exc:
        checks.append(
            DiagnosticCheck(
                label="Канал доступен через Telegram API",
                ok=False,
                details=_readable_error(exc),
            )
        )
        recommendations.extend(
            [
                "Проверьте правильность chat_id в разделе каналов.",
                "Убедитесь, что бот добавлен в нужный канал.",
            ]
        )
        return ChannelDiagnosticResult(
            channel_id=channel.id,
            title=title,
            telegram_chat_id=channel.telegram_chat_id,
            username=channel.username,
            is_active=channel.is_active,
            checks=tuple(checks),
            recommendations=tuple(recommendations),
        )

    live_title = getattr(chat, "title", None) or getattr(chat, "full_name", None) or title
    live_username = getattr(chat, "username", None)
    checks.append(
        DiagnosticCheck(
            label="Канал найден",
            ok=True,
            details=escape(live_title),
        )
    )

    try:
        member = await bot.get_chat_member(chat.id, bot_id)
    except Exception as exc:
        checks.append(
            DiagnosticCheck(
                label="Статус бота в канале",
                ok=False,
                details=_readable_error(exc),
            )
        )
        recommendations.extend(
            [
                "Добавьте бота в канал, если его там нет.",
                "Если бот уже добавлен, проверьте, что его не исключили из канала.",
            ]
        )
        return ChannelDiagnosticResult(
            channel_id=channel.id,
            title=live_title,
            telegram_chat_id=chat.id,
            username=live_username,
            is_active=channel.is_active,
            checks=tuple(checks),
            recommendations=tuple(recommendations),
        )

    status = str(getattr(member, "status", "unknown"))
    in_channel = status not in {"left", "kicked"}
    is_admin = status in {"administrator", "creator"}
    can_invite = is_admin and (
        status == "creator" or bool(getattr(member, "can_invite_users", False))
    )
    can_restrict = is_admin and (
        status == "creator"
        or bool(getattr(member, "can_restrict_members", False))
        or bool(getattr(member, "can_manage_chat", False))
    )

    checks.extend(
        [
            DiagnosticCheck(
                label="Бот состоит в канале",
                ok=in_channel,
                details=_member_status_label(status),
            ),
            DiagnosticCheck(
                label="Бот администратор",
                ok=is_admin,
                details=_member_status_label(status),
            ),
            DiagnosticCheck(
                label="Может создавать invite links",
                ok=can_invite,
                details="да" if can_invite else "нет",
            ),
            DiagnosticCheck(
                label="Может ограничивать пользователей",
                ok=can_restrict,
                details="да" if can_restrict else "нет",
            ),
            DiagnosticCheck(
                label="Синхронизация snapshot invite",
                ok=channel.invite_users_permission == can_invite,
                details=(
                    f"store={'да' if channel.invite_users_permission else 'нет'}, "
                    f"live={'да' if can_invite else 'нет'}"
                ),
            ),
            DiagnosticCheck(
                label="Синхронизация snapshot restrict",
                ok=channel.ban_users_permission == can_restrict,
                details=(
                    f"store={'да' if channel.ban_users_permission else 'нет'}, "
                    f"live={'да' if can_restrict else 'нет'}"
                ),
            ),
        ]
    )

    if not in_channel:
        recommendations.append("Добавьте бота обратно в канал.")
    if in_channel and not is_admin:
        recommendations.append("Выдайте боту права администратора.")
    if is_admin and not can_invite:
        recommendations.append("Включите право на создание invite links.")
    if is_admin and not can_restrict:
        recommendations.append("Включите право на restrict/ban пользователей.")

    permissions_mismatch = (
        channel.invite_users_permission != can_invite
        or channel.ban_users_permission != can_restrict
    )
    if permissions_mismatch:
        recommendations.append(
            "Обновите snapshot канала через раздел «Каналы» или повторной проверкой."
        )
    if not recommendations and all(check.ok for check in checks):
        recommendations.append(
            "Всё готово: канал можно безопасно использовать для invite и revoke flow."
        )

    return ChannelDiagnosticResult(
        channel_id=channel.id,
        title=live_title,
        telegram_chat_id=chat.id,
        username=live_username,
        is_active=channel.is_active,
        checks=tuple(checks),
        recommendations=tuple(recommendations),
    )


def render_channel_diagnostics_report(report: ChannelDiagnosticsReport) -> str:
    lines = ["🧪 Проверка каналов", ""]

    if report.bot_username is not None:
        lines.append(f"✅ Бот подключен: @{escape(report.bot_username)}")
    else:
        lines.append(f"❌ getMe: {escape(report.get_me_error or 'неизвестная ошибка')}")

    if not report.results:
        lines.extend(
            [
                "",
                "Каналы ещё не добавлены.",
                "Откройте раздел «Каналы» в админке и подключите хотя бы один канал.",
            ]
        )
        return "\n".join(lines)

    issues = sum(1 for result in report.results if not result.overall_ok)
    problem_marker = "✅" if issues == 0 and report.get_me_error is None else "⚠️"
    lines.append(f"📦 Каналов в проверке: {len(report.results)}")
    lines.append(f"{problem_marker} Проблемных каналов: {issues}")

    for result in report.results:
        lines.extend(
            [
                "",
                f"📣 {escape(result.title)}{' (выключен)' if not result.is_active else ''}",
                f"Chat ID: <code>{result.telegram_chat_id}</code>",
            ]
        )
        if result.username:
            lines.append(f"Username: @{escape(result.username.lstrip('@'))}")
        for check in result.checks:
            lines.append(f"{'✅' if check.ok else '❌'} {check.label}: {escape(check.details)}")
        if result.recommendations:
            lines.append("")
            lines.append("Что сделать:")
            for index, recommendation in enumerate(result.recommendations, start=1):
                lines.append(f"{index}. {escape(recommendation)}")

    lines.extend(
        [
            "",
            f"Итог: {'всё готово' if report.overall_ok else 'есть проблемы, требующие внимания'}.",
        ]
    )
    return "\n".join(lines)


def _member_status_label(status: str) -> str:
    labels = {
        "creator": "владелец",
        "administrator": "администратор",
        "member": "участник",
        "left": "вышел",
        "kicked": "исключён",
        "restricted": "ограничен",
        "unknown": "неизвестно",
    }
    return labels.get(status, status or "неизвестно")


def _readable_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if "chat not found" in lowered or "not found" in lowered:
        return "канал не найден или bot не видит его"
    if "forbidden" in lowered:
        return "Telegram API запретил доступ"
    if "member" in lowered and "not" in lowered:
        return "бот не состоит в канале"
    return message
