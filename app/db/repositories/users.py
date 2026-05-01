from __future__ import annotations

from datetime import UTC, datetime

from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.admin_roles import is_admin_role, normalize_admin_role
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

    async def get_by_username(self, username: str) -> User | None:
        normalized = username.strip().removeprefix("@").lower()
        if not normalized:
            return None
        result = await self._session.execute(
            select(User).where(func.lower(User.username) == normalized)
        )
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

    async def upsert_from_identity(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        admin_ids: set[int],
    ) -> User:
        existing = await self.get_by_telegram_id(telegram_id)
        if existing is None:
            existing = User(telegram_id=telegram_id)
            self._session.add(existing)

        existing.username = username
        existing.first_name = first_name
        existing.last_name = last_name
        existing.language_code = language_code

        fallback_owner = telegram_id in admin_ids
        if fallback_owner:
            existing.role = "owner"
        else:
            existing.role = normalize_admin_role(existing.role)
        existing.is_admin = is_admin_role(existing.role)
        existing.last_seen_at = datetime.now(UTC)
        if not existing.referral_code:
            existing.referral_code = build_referral_code(telegram_id)
        return existing

    async def upsert_from_telegram_user(
        self, telegram_user: TelegramUser, *, admin_ids: set[int]
    ) -> User:
        return await self.upsert_from_identity(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
            admin_ids=admin_ids,
        )

    async def set_blocked(self, user: User, *, is_blocked: bool) -> User:
        user.is_blocked = is_blocked
        return user

    async def set_role(self, user: User, *, role: str) -> User:
        normalized = normalize_admin_role(role)
        user.role = normalized
        user.is_admin = is_admin_role(normalized)
        return user
