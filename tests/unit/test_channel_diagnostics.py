from __future__ import annotations

from types import SimpleNamespace

from app.db.models import Channel
from app.services.channel_diagnostics import (
    build_channel_diagnostics_report,
    render_channel_diagnostics_report,
)


class FakeBot:
    def __init__(
        self,
        *,
        me=None,
        chat=None,
        member=None,
        me_error: Exception | None = None,
        chat_error: Exception | None = None,
        member_error: Exception | None = None,
    ) -> None:
        self._me = me or SimpleNamespace(id=500, username="diag_bot")
        self._chat = chat or SimpleNamespace(
            id=-1001234567890,
            title="Main Channel",
            username="main_channel",
        )
        self._member = member or SimpleNamespace(
            status="administrator",
            can_invite_users=True,
            can_restrict_members=True,
            can_manage_chat=True,
        )
        self._me_error = me_error
        self._chat_error = chat_error
        self._member_error = member_error

    async def get_me(self):
        if self._me_error is not None:
            raise self._me_error
        return self._me

    async def get_chat(self, reference):
        if self._chat_error is not None:
            raise self._chat_error
        return self._chat

    async def get_chat_member(self, chat_id, user_id):
        if self._member_error is not None:
            raise self._member_error
        return self._member


def _channel() -> Channel:
    return Channel(
        id=1,
        telegram_chat_id=-1001234567890,
        username="main_channel",
        title="Основной канал",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )


async def test_channel_diagnostics_all_ok() -> None:
    report = await build_channel_diagnostics_report(FakeBot(), [_channel()])
    text = render_channel_diagnostics_report(report)

    assert report.bot_username == "diag_bot"
    assert report.overall_ok is True
    assert "✅ Бот подключен: @diag_bot" in text
    assert "✅ Бот администратор: администратор" in text
    assert "Итог: всё готово." in text


async def test_channel_diagnostics_detects_missing_permissions() -> None:
    member = SimpleNamespace(
        status="administrator",
        can_invite_users=False,
        can_restrict_members=False,
        can_manage_chat=False,
    )
    report = await build_channel_diagnostics_report(FakeBot(member=member), [_channel()])
    text = render_channel_diagnostics_report(report)

    assert report.overall_ok is False
    assert "❌ Может создавать invite links: нет" in text
    assert "❌ Может ограничивать пользователей: нет" in text
    assert "Включите право на создание invite links." in text
    assert "Включите право на restrict/ban пользователей." in text


async def test_channel_diagnostics_handles_chat_lookup_error() -> None:
    report = await build_channel_diagnostics_report(
        FakeBot(chat_error=RuntimeError("chat not found")),
        [_channel()],
    )
    text = render_channel_diagnostics_report(report)

    assert report.overall_ok is False
    assert "❌ Канал доступен через Telegram API: канал не найден или bot не видит его" in text
    assert "Проверьте правильность chat_id" in text


async def test_channel_diagnostics_handles_get_me_error() -> None:
    report = await build_channel_diagnostics_report(
        FakeBot(me_error=RuntimeError("forbidden")),
        [_channel()],
    )
    text = render_channel_diagnostics_report(report)

    assert report.bot_username is None
    assert report.overall_ok is False
    assert "❌ getMe: Telegram API запретил доступ" in text
    assert "Live-проверка: Пропущена: getMe недоступен." in text


async def test_channel_diagnostics_reports_empty_channel_list() -> None:
    report = await build_channel_diagnostics_report(FakeBot(), [])
    text = render_channel_diagnostics_report(report)

    assert "Каналы ещё не добавлены." in text
