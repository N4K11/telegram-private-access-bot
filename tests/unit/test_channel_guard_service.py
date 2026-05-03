from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.db.models import Channel
from app.services.channel_guard_service import (
    reset_channel_guard_state,
    run_channel_guard,
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
        self._me = me or SimpleNamespace(id=500, username='guard_bot')
        self._chat = chat or SimpleNamespace(
            id=-1001234567890,
            title='Main Channel',
            username='main_channel',
        )
        self._member = member or SimpleNamespace(
            status='administrator',
            can_invite_users=True,
            can_restrict_members=True,
            can_manage_chat=True,
        )
        self._me_error = me_error
        self._chat_error = chat_error
        self._member_error = member_error
        self.sent_messages: list[tuple[int, str]] = []

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

    async def send_message(self, chat_id: int, text: str):
        self.sent_messages.append((chat_id, text))


@pytest.fixture(autouse=True)
def reset_guard_state_fixture() -> None:
    reset_channel_guard_state()


def _channel() -> Channel:
    return Channel(
        id=1,
        telegram_chat_id=-1001234567890,
        username='main_channel',
        title='Основной канал',
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )


async def test_channel_guard_detects_bot_kicked() -> None:
    bot = FakeBot(member=SimpleNamespace(status='kicked'))

    result = await run_channel_guard(bot=bot, channels=[_channel()], admin_ids=[42])

    assert result.has_issues is True
    assert any(issue.code == 'bot_kicked' for issue in result.issues)
    assert bot.sent_messages
    assert 'Бот больше не состоит в канале.' in bot.sent_messages[0][1]


async def test_channel_guard_detects_missing_permissions() -> None:
    member = SimpleNamespace(
        status='administrator',
        can_invite_users=False,
        can_restrict_members=False,
        can_manage_chat=False,
    )
    bot = FakeBot(member=member)

    result = await run_channel_guard(bot=bot, channels=[_channel()], admin_ids=[42])

    assert result.has_issues is True
    assert {issue.code for issue in result.issues} == {
        'no_invite_permission',
        'no_restrict_permission',
    }
    assert 'Проверьте /admin_channel_check.' in result.alert_text


async def test_channel_guard_notifies_admin_once_for_same_problem() -> None:
    bot = FakeBot(member=SimpleNamespace(status='member'))

    first = await run_channel_guard(bot=bot, channels=[_channel()], admin_ids=[42])
    second = await run_channel_guard(bot=bot, channels=[_channel()], admin_ids=[42])

    assert first.alert_sent is True
    assert second.suppressed is True
    assert len(bot.sent_messages) == 1
