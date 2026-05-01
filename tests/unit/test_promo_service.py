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
    get_promo_stats,
    list_promo_codes,
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
    title: str = "Основной канал",
) -> tuple[User, Tariff]:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User {telegram_id}",
        is_admin=False,
        role="user",
    )
    channel = Channel(
        telegram_chat_id=-1001234567890 - telegram_id,
        title=title,
        invite_users_permission=True,
        ban_users_permission=True,
        is_active=True,
    )
    session.add_all([user, channel])
    await session.flush()

    tariff = Tariff(
        name=f"VIP {telegram_id}",
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


async def test_apply_promo_rejects_disabled_expired_and_not_yet_valid() -> None:
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
                valid_until="2026-05-01T11:00:00+00:00",
            ),
        )

        future = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="WAIT50",
                promo_type="discount_stars",
                value="50",
                max_uses="5",
                tariff_id=str(tariff.id),
                valid_from="2026-05-01T13:00:00+00:00",
            ),
        )
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
        with pytest.raises(PromoCodeError, match="ещё не активен"):
            await apply_promo_code(
                session,
                user_id=user.id,
                code=future.code,
                now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            )
    finally:
        await _close_session(session, engine)


async def test_first_purchase_only_rejects_after_paid_payment() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session)
        session.add(
            Payment(
                user_id=user.id,
                tariff_id=tariff.id,
                channel_id=tariff.channel_id,
                amount=250,
                currency="XTR",
                provider="telegram_stars",
                invoice_payload="subscription:1",
                provider_payment_charge_id="provider-paid",
                paid_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
                status="paid",
            )
        )
        promo = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="FIRST20",
                promo_type="discount_percent",
                value="20",
                max_uses="5",
                tariff_id=str(tariff.id),
                first_purchase_only="1",
            ),
        )
        await session.commit()

        with pytest.raises(PromoCodeError, match="только до первой успешной оплаты"):
            await apply_promo_code(session, user_id=user.id, code=promo.code)
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


async def test_discount_promo_changes_invoice_amount_and_rejects_wrong_tariff() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session, telegram_id=42)
        _, other_tariff = await _seed_user_channel_tariff(
            session,
            telegram_id=77,
            title="Другой канал",
        )
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

        wrong_quote = await get_pending_discount_quote_for_tariff(
            session,
            user_id=user.id,
            tariff=other_tariff,
        )
        assert wrong_quote is None
    finally:
        await _close_session(session, engine)


async def test_per_user_limit_allows_multiple_uses_then_rejects() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session, telegram_id=42)
        promo = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="FREE2X",
                promo_type=PROMO_TYPE_FREE_DAYS,
                value="2",
                max_uses="5",
                tariff_id=str(tariff.id),
                per_user_limit="2",
            ),
        )
        await session.commit()

        await apply_promo_code(session, user_id=user.id, code=promo.code)
        await session.commit()
        await apply_promo_code(session, user_id=user.id, code=promo.code)
        await session.commit()

        with pytest.raises(PromoCodeError, match="Персональный лимит"):
            await apply_promo_code(session, user_id=user.id, code=promo.code)

        redemptions = list((await session.execute(select(PromoRedemption))).scalars())
        assert len(redemptions) == 2
        assert all(redemption.status == "consumed" for redemption in redemptions)
    finally:
        await _close_session(session, engine)


async def test_max_uses_rejects_when_global_limit_is_exhausted() -> None:
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

        with pytest.raises(PromoCodeError, match="Лимит использований"):
            await apply_promo_code(session, user_id=user_two.id, code=promo.code)
    finally:
        await _close_session(session, engine)


async def test_list_and_stats_are_read_only() -> None:
    session, engine = await _create_session()
    try:
        user, tariff = await _seed_user_channel_tariff(session)
        promo = await create_promo_code(
            session,
            actor_user_id=None,
            draft=parse_promo_draft(
                code="SPRING50",
                promo_type="discount_stars",
                value="50",
                max_uses="3",
                tariff_id=str(tariff.id),
                campaign_name="Spring_Sale",
            ),
        )
        await session.commit()

        await apply_promo_code(session, user_id=user.id, code=promo.code)
        await session.commit()

        promos = await list_promo_codes(session, search="spring", limit=10)
        stats = await get_promo_stats(session, code=promo.code)

        assert len(promos) == 1
        assert promos[0].code == promo.code
        assert stats.pending_count == 1
        assert stats.consumed_count == 0
        assert stats.total_uses == 1
        assert not session.dirty
    finally:
        await _close_session(session, engine)



