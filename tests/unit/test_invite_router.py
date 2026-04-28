from __future__ import annotations

from datetime import UTC, datetime

from app.bot.routers.user.invites import issue_invite_link_handler
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 42) -> None:
        self.id = user_id
        self.first_name = "Anna"


class DummyMessage:
    def __init__(self) -> None:
        self.answer_calls: list[str] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append(text)


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = DummyUser()
        self.message = DummyMessage()
        self.answer_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_calls.append((args, kwargs))


class FailingBot:
    async def create_chat_invite_link(self, **kwargs):
        raise RuntimeError("telegram failure")


async def test_issue_invite_router_reports_friendly_error() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    callback = DummyCallback("menu:user:invite:1")
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "default_invite_link_ttl_hours": 24,
        }
    )

    async with session_factory() as session:
        user = User(telegram_id=42, first_name="Anna", is_admin=False, role="user")
        channel = Channel(
            telegram_chat_id=-1001234567890,
            title="Основной канал",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        session.add_all([user, channel])
        await session.flush()

        tariff = Tariff(
            name="VIP 30",
            price_stars=250,
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
        session.add(tariff)
        await session.flush()

        session.add(
            Subscription(
                id=1,
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                status="active",
                source="purchase",
                started_at=datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
                expires_at=datetime(2026, 5, 27, 12, 0, tzinfo=UTC),
            )
        )
        await session.commit()

        await issue_invite_link_handler(
            callback,
            session=session,
            settings=settings,
            bot=FailingBot(),
        )

    await engine.dispose()

    assert callback.message.answer_calls == []
    assert callback.answer_calls
    args, kwargs = callback.answer_calls[-1]
    assert args == (
        "Не удалось создать ссылку доступа. Попробуйте позже или используйте /paysupport.",
    )
    assert kwargs == {"show_alert": True}