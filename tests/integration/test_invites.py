from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, InviteLink, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.invites import InviteLinkError, issue_subscription_invite_link


class DummyInvite:
    def __init__(self, invite_link: str, expire_date: datetime, member_limit: int = 1) -> None:
        self.invite_link = invite_link
        self.expire_date = expire_date
        self.member_limit = member_limit


class DummyBot:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_chat_invite_link(self, **kwargs):
        self.calls.append(kwargs)
        return DummyInvite(
            invite_link="https://t.me/+invite-1",
            expire_date=kwargs["expire_date"],
            member_limit=kwargs.get("member_limit") or 1,
        )


async def _create_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    return session_factory(), engine


async def _close_session(session: AsyncSession, engine) -> None:
    await session.close()
    await engine.dispose()


async def _seed_subscription(
    session: AsyncSession,
    *,
    started_at: datetime,
    expires_at: datetime,
) -> tuple[User, Subscription]:
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

    subscription = Subscription(
        user_id=user.id,
        tariff_id=tariff.id,
        channel_id=channel.id,
        status="active",
        source="purchase",
        started_at=started_at,
        expires_at=expires_at,
    )
    session.add(subscription)
    await session.commit()
    return user, subscription


async def test_issue_invite_requires_active_subscription() -> None:
    session, engine = await _create_session()
    try:
        bot = DummyBot()
        with pytest.raises(InviteLinkError):
            await issue_subscription_invite_link(
                session,
                bot,
                user_id=1,
                subscription_id=1,
                ttl_hours=24,
                now=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
            )
    finally:
        await _close_session(session, engine)


async def test_issue_invite_creates_and_reuses_active_link() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        user, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
        )
        bot = DummyBot()

        first = await issue_subscription_invite_link(
            session,
            bot,
            user_id=user.id,
            subscription_id=subscription.id,
            ttl_hours=24,
            now=now,
        )
        await session.commit()

        second = await issue_subscription_invite_link(
            session,
            bot,
            user_id=user.id,
            subscription_id=subscription.id,
            ttl_hours=24,
            now=now + timedelta(hours=1),
        )
        await session.commit()

        invites = list((await session.execute(select(InviteLink))).scalars())

        assert first.is_reused is False
        assert second.is_reused is True
        assert first.invite.id == second.invite.id
        assert len(invites) == 1
        assert len(bot.calls) == 1
    finally:
        await _close_session(session, engine)


async def test_issue_invite_recreates_expired_link() -> None:
    session, engine = await _create_session()
    try:
        now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
        user, subscription = await _seed_subscription(
            session,
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
        )
        session.add(
            InviteLink(
                user_id=user.id,
                channel_id=subscription.channel_id,
                subscription_id=subscription.id,
                invite_link="https://t.me/+expired",
                expire_at=now - timedelta(minutes=1),
                member_limit=1,
                is_revoked=False,
            )
        )
        await session.commit()

        bot = DummyBot()
        result = await issue_subscription_invite_link(
            session,
            bot,
            user_id=user.id,
            subscription_id=subscription.id,
            ttl_hours=24,
            now=now,
        )
        await session.commit()

        invites = list((await session.execute(select(InviteLink))).scalars())

        assert result.is_reused is False
        assert result.invite.invite_link == "https://t.me/+invite-1"
        assert len(invites) == 2
        assert len(bot.calls) == 1
    finally:
        await _close_session(session, engine)