from __future__ import annotations

from datetime import UTC, datetime

from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.utils.referrals import build_referral_code


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[User]:
        result = await self._session.execute(
            select(User).order_by(User.last_seen_at.desc(), User.id.desc())
        )
        return list(result.scalars())

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, referral_code: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.referral_code == referral_code.upper())
        )
        return result.scalar_one_or_none()

    async def count_rewarded_referrals(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.count(User.id))
            .where(User.referred_by_user_id == user_id)
            .where(User.referral_reward_granted_at.is_not(None))
        )
        value = result.scalar_one()
        return int(value or 0)

    async def upsert_from_telegram_user(
        self, telegram_user: TelegramUser, *, admin_ids: set[int]
    ) -> User:
        existing = await self.get_by_telegram_id(telegram_user.id)
        if existing is None:
            existing = User(telegram_id=telegram_user.id)
            self._session.add(existing)

        existing.username = telegram_user.username
        existing.first_name = telegram_user.first_name
        existing.last_name = telegram_user.last_name
        existing.language_code = telegram_user.language_code
        existing.is_admin = telegram_user.id in admin_ids
        existing.role = "owner" if telegram_user.id in admin_ids else "user"
        existing.last_seen_at = datetime.now(UTC)
        if not existing.referral_code:
            existing.referral_code = build_referral_code(telegram_user.id)
        return existing

    async def set_blocked(self, user: User, *, is_blocked: bool) -> User:
        user.is_blocked = is_blocked
        return user
