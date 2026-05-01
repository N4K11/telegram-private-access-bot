from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.user.referrals import my_referrals_command, referrals_section
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.utils.referrals import build_referral_code


class DummyUser:
    def __init__(self, user_id: int, *, first_name: str, username: str | None = None) -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = username
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self, *, user_id: int, first_name: str, username: str | None = None) -> None:
        self.from_user = DummyUser(user_id, first_name=first_name, username=username)
        self.answer_calls: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallbackMessage:
    def __init__(self) -> None:
        self.photo = None
        self.edit_text_calls: list[tuple[str, object | None]] = []
        self.answer_calls: list[tuple[str, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_text_calls.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))


class DummyCallback:
    def __init__(self, *, user_id: int, username: str | None = None) -> None:
        self.from_user = DummyUser(user_id, first_name="Руслан", username=username)
        self.message = DummyCallbackMessage()
        self.answer_calls: list[tuple[str | None, bool]] = []
        self.data = "menu:user:referrals"

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answer_calls.append((text, show_alert))


class FakeBot:
    async def get_me(self):
        class Me:
            username = "PrivatAir_bot"

        return Me()


async def _create_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    session = session_factory()
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


async def _close_session(session: AsyncSession) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    await session.close()
    await engine.dispose()


async def _seed_user(session: AsyncSession) -> User:
    channel = Channel(
        telegram_chat_id=-1001234500100,
        title="User referrals",
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add(channel)
    await session.flush()
    tariff = Tariff(
        name="VIP",
        price_stars=199,
        duration_days=30,
        sort_order=10,
        is_active=True,
        channel_id=channel.id,
    )
    session.add(tariff)
    await session.flush()
    user = User(
        telegram_id=123456,
        first_name="Руслан",
        username="ruslan",
        referral_code=build_referral_code(123456),
        pending_referral_reward_days=5,
        role="user",
    )
    invited = User(
        telegram_id=123457,
        first_name="Friend",
        role="user",
        referred_by_user_id=1,
        referred_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )
    session.add(user)
    await session.flush()
    invited.referred_by_user_id = user.id
    session.add(invited)
    await session.commit()
    return user


async def test_my_referrals_command_renders_dashboard() -> None:
    session = await _create_session()
    try:
        await _seed_user(session)
        message = DummyMessage(user_id=123456, first_name="Руслан", username="ruslan")
        settings = Settings.model_validate(
            {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"}
        )

        await my_referrals_command(message, session, settings, FakeBot())

        assert len(message.answer_calls) == 1
        text, _ = message.answer_calls[0]
        assert "Реферальная программа" in text
        assert "Приглашено друзей: 1" in text
        assert "Ожидает начисления: 5 дн." in text
        assert "https://t.me/PrivatAir_bot?start=ref_" in text
    finally:
        await _close_session(session)


async def test_referrals_section_edits_existing_message() -> None:
    session = await _create_session()
    try:
        await _seed_user(session)
        callback = DummyCallback(user_id=123456, username="ruslan")
        settings = Settings.model_validate(
            {"bot_token": "123:token", "admin_ids": [755815181], "timezone": "UTC"}
        )

        await referrals_section(callback, session, settings, FakeBot())

        assert len(callback.message.edit_text_calls) == 1
        text, _ = callback.message.edit_text_calls[0]
        assert "Реферальная программа" in text
        assert callback.answer_calls == [(None, False)]
    finally:
        await _close_session(session)
