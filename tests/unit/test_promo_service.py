from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Channel, Payment, PromoRedemption, Subscription, Tariff, User
from app.db.session import create_async_engine, create_session_factory
from app.services.promo_service import (
    PROMO_TYPE_DISCOUNT_STARS,
    PROMO_TYPE_FREE_DAYS,
    PromoCodeError,
    apply_promo_code,
    create_promo_code,
    get_pending_discount_quote_for_tariff,
    parse_promo_draft,
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


async def _seed_user_channel_tariff(
    session: AsyncSession,
    *,
    telegram_id: int = 42,
) -> tuple[User, Tariff]:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User {telegram_id}",
        is_admin=False,
        role="user",
    )
    channel = Channel(
        telegram_chat_id=-1001234567890 - telegram_id,
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
    await session.commit()
    return user, tariff


async def test_apply_promo_rejects_not_found() -> None:
    session, engine = await _create_session()
    try:
        user, _ = await _seed_user_channel_tariff(session)
        with pytest.raises(PromoCodeError, match="Промокод не найден"):
            await apply_promo_code(session, user_id=user.id, code="MISSING")
    finally:
        await _close_session(session, engine)


async def test_apply_promo_rejects_disabled_and_expired() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session)
        disabled = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="OFF50",
                promo_type="discount_stars",
                value="50",
                max_uses="5",
                tariff_id=str(tariff.id),
            ),
        )
        disabled.is_active = False

        expired = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="OLD50",
                promo_type="discount_stars",
                value="50",
                max_uses="5",
                tariff_id=str(tariff.id),
                valid_days="1",
            ),
            now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        )
        expired.expires_at = datetime(2026, 5, 1, 11, 0, tzinfo=UTC)
        await session.commit()

        with pytest.raises(PromoCodeError, match="Промокод отключён"):
            await apply_promo_code(session, user_id=user.id, code=disabled.code)
        with pytest.raises(PromoCodeError, match="Срок действия промокода истёк"):
            await apply_promo_code(
                session,
                user_id=user.id,
                code=expired.code,
                now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            )
    finally:
        await _close_session(session, engine)


async def test_free_days_grants_subscription_without_fake_payment() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session)
        promo = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="FREE7",
                promo_type="free_days",
                value="7",
                max_uses="1",
                tariff_id=str(tariff.id),
            ),
        )
        await session.commit()

        result = await apply_promo_code(
            session,
            user_id=user.id,
            code=promo.code,
            now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        )
        await session.commit()

        subscriptions = list((await session.execute(select(Subscription))).scalars())
        payments = list((await session.execute(select(Payment))).scalars())
        redemptions = list((await session.execute(select(PromoRedemption))).scalars())

        assert result.action == "granted_free_days"
        assert len(subscriptions) == 1
        assert subscriptions[0].source == "promo"
        assert subscriptions[0].expires_at == datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
        assert len(payments) == 0
        assert len(redemptions) == 1
        assert redemptions[0].status == "consumed"
    finally:
        await _close_session(session, engine)


async def test_discount_promo_changes_invoice_amount() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session)
        promo = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="MINUS50",
                promo_type="discount_stars",
                value="50",
                max_uses="2",
                tariff_id=str(tariff.id),
            ),
        )
        await session.commit()

        result = await apply_promo_code(session, user_id=user.id, code=promo.code)
        quote = await get_pending_discount_quote_for_tariff(
            session,
            user_id=user.id,
            tariff=tariff,
        )

        assert result.action == "pending_discount"
        assert quote is not None
        assert quote.promo_code.promo_type == PROMO_TYPE_DISCOUNT_STARS
        assert quote.original_amount == 250
        assert quote.final_amount == 200
        assert quote.savings_amount == 50
    finally:
        await _close_session(session, engine)


async def test_max_uses_and_repeated_use_by_same_user_are_rejected() -> None:
    session, engine = await _create_session()
    try:
        user_one, tariff = await _seed_user_channel_tariff(session, telegram_id=42)
        user_two, _ = await _seed_user_channel_tariff(session, telegram_id=77)
        promo = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="FREE3",
                promo_type=PROMO_TYPE_FREE_DAYS,
                value="3",
                max_uses="1",
                tariff_id=str(tariff.id),
            ),
        )
        await session.commit()

        await apply_promo_code(
            session,
            user_id=user_one.id,
            code=promo.code,
            now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        )
        await session.commit()

        with pytest.raises(PromoCodeError, match="уже использован"):
            await apply_promo_code(session, user_id=user_one.id, code=promo.code)
        with pytest.raises(PromoCodeError, match="Лимит использований"):
            await apply_promo_code(session, user_id=user_two.id, code=promo.code)
    finally:
        await _close_session(session, engine)


