# ruff: noqa: E501
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin import AdminFilter
from app.bot.routers.admin.finance import admin_finance, export_finance_report, finance_dashboard
from app.config import Settings
from app.db.base import Base
from app.db.models import Channel, Payment, Tariff, User
from app.db.session import create_async_engine, create_session_factory


class DummyUser:
    def __init__(self, user_id: int = 755815181, first_name: str = "Admin") -> None:
        self.id = user_id
        self.first_name = first_name
        self.username = "admin"
        self.last_name = None
        self.language_code = "ru"


class DummyMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.from_user = DummyUser()
        self.answer_calls: list[tuple[str, object | None]] = []
        self.edit_calls: list[tuple[str, object | None]] = []
        self.document_calls: list[tuple[object, str | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answer_calls.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edit_calls.append((text, reply_markup))

    async def answer_document(self, document, caption: str | None = None) -> None:
        self.document_calls.append((document, caption))


class DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = DummyMessage()
        self.from_user = DummyUser()
        self.answer_count = 0
        self.answer_texts: list[str] = []

    async def answer(self, text: str | None = None, **kwargs) -> None:
        self.answer_count += 1
        if text is not None:
            self.answer_texts.append(text)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        user = User(telegram_id=42, first_name="Anna", role="user")
        db_session.add(user)
        await db_session.flush()

        channel = Channel(
            telegram_chat_id=-1001234567890,
            title="Main channel",
            invite_users_permission=True,
            ban_users_permission=True,
            is_active=True,
        )
        db_session.add(channel)
        await db_session.flush()

        tariff = Tariff(
            name="VIP 30",
            price_stars=250,
            price_crypto=Decimal("1.25"),
            duration_days=30,
            sort_order=10,
            is_active=True,
            channel_id=channel.id,
        )
        db_session.add(tariff)
        await db_session.flush()

        db_session.add(
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=channel.id,
                amount=250,
                currency="Stars",
                provider="telegram_stars",
                telegram_payment_charge_id="tg-paid-1",
                provider_payment_charge_id="provider-paid-1",
                invoice_payload="stars:tariff:1",
                paid_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
                status="paid",
            )
        )
        await db_session.commit()
        yield db_session

    await engine.dispose()


def _flatten_button_texts(markup) -> list[str]:
    texts: list[str] = []
    for row in markup.inline_keyboard:
        for button in row:
            texts.append(button.text)
    return texts


async def test_admin_finance_command_renders_dashboard(session: AsyncSession) -> None:
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )
    message = DummyMessage("/admin_finance")

    await admin_finance(message, session, settings)

    assert message.answer_calls
    text, markup = message.answer_calls[0]
    assert "\u0424\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u0430\u044f \u043f\u0430\u043d\u0435\u043b\u044c" in text
    assert "Stars" in text
    assert all(label.startswith("CSV:") for label in _flatten_button_texts(markup)[:4])


async def test_finance_dashboard_callback_renders_edit(session: AsyncSession) -> None:
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )
    callback = DummyCallback("menu:admin:payments")

    await finance_dashboard(callback, session, settings)

    assert callback.message.edit_calls
    text, _ = callback.message.edit_calls[0]
    assert "\u0424\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u0430\u044f \u043f\u0430\u043d\u0435\u043b\u044c" in text
    assert callback.answer_count == 1


async def test_finance_export_sends_csv_document(session: AsyncSession) -> None:
    settings = Settings.model_validate(
        {
            "bot_token": "123:token",
            "admin_ids": [755815181],
            "timezone": "UTC",
        }
    )
    callback = DummyCallback("menu:admin:finance:export:day")

    await export_finance_report(callback, session, settings)

    assert callback.message.document_calls
    document, caption = callback.message.document_calls[0]
    assert document.filename.startswith("finance-report-day-")
    assert document.filename.endswith(".csv")
    assert "stars_revenue" in document.data.decode("utf-8")
    assert caption.endswith(": day")
    assert callback.answer_texts == ["CSV \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d."]


async def test_admin_finance_filter_rejects_non_admin() -> None:
    event = type("Event", (), {"from_user": DummyUser(user_id=1)})()
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [755815181]})

    result = await AdminFilter()(event, settings)

    assert result is False

