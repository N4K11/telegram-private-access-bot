from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel
from app.services.channels import ChannelSnapshot


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Channel]:
        result = await self._session.execute(
            select(Channel).order_by(
                Channel.is_active.desc(),
                Channel.title.asc(),
                Channel.id.asc(),
            )
        )
        return list(result.scalars())

    async def list_active(self) -> list[Channel]:
        result = await self._session.execute(select(Channel).where(Channel.is_active.is_(True)))
        return list(result.scalars())

    async def list_available_for_tariffs(self) -> list[Channel]:
        result = await self._session.execute(
            select(Channel)
            .where(Channel.is_active.is_(True))
            .where(Channel.invite_users_permission.is_(True))
            .where(Channel.ban_users_permission.is_(True))
            .order_by(Channel.title.asc(), Channel.id.asc())
        )
        return list(result.scalars())

    async def get_by_id(self, channel_id: int) -> Channel | None:
        return await self._session.get(Channel, channel_id)

    async def get_by_chat_id(self, chat_id: int) -> Channel | None:
        result = await self._session.execute(
            select(Channel).where(Channel.telegram_chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Channel | None:
        result = await self._session.execute(select(Channel).where(Channel.username == username))
        return result.scalar_one_or_none()

    async def upsert_snapshot(self, snapshot: ChannelSnapshot) -> Channel:
        channel = await self.get_by_chat_id(snapshot.telegram_chat_id)
        if channel is None and snapshot.username is not None:
            channel = await self.get_by_username(snapshot.username)
        if channel is None:
            channel = Channel(
                telegram_chat_id=snapshot.telegram_chat_id,
                title=snapshot.title,
                username=snapshot.username,
            )
            self._session.add(channel)

        channel.telegram_chat_id = snapshot.telegram_chat_id
        channel.title = snapshot.title
        channel.username = snapshot.username
        channel.invite_users_permission = snapshot.invite_users_permission
        channel.ban_users_permission = snapshot.ban_users_permission
        return channel

    async def rename(self, channel: Channel, title: str) -> Channel:
        channel.title = title.strip()
        return channel

    async def set_active(self, channel: Channel, *, is_active: bool) -> Channel:
        channel.is_active = is_active
        return channel