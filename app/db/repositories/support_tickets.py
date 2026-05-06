from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import SupportMessage, SupportTicket


class SupportTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_ticket(
        self,
        *,
        user_id: int,
        category: str,
        priority: str,
        created_at: datetime,
    ) -> SupportTicket:
        ticket = SupportTicket(
            user_id=user_id,
            category=category,
            priority=priority,
            status="open",
            last_user_message_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
        self._session.add(ticket)
        await self._session.flush()
        return ticket

    async def add_message(
        self,
        *,
        ticket_id: int,
        sender_user_id: int,
        body: str,
        is_admin: bool,
        created_at: datetime,
    ) -> SupportMessage:
        message = SupportMessage(
            ticket_id=ticket_id,
            sender_user_id=sender_user_id,
            body=body,
            is_admin=is_admin,
            created_at=created_at,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def get_by_id(
        self,
        ticket_id: int,
        *,
        with_messages: bool = True,
    ) -> SupportTicket | None:
        stmt = (
            select(SupportTicket)
            .execution_options(populate_existing=True)
            .where(SupportTicket.id == ticket_id)
            .execution_options(populate_existing=True)
        )
        stmt = stmt.options(selectinload(SupportTicket.user))
        if with_messages:
            stmt = stmt.options(
                selectinload(SupportTicket.messages).selectinload(SupportMessage.sender)
            )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_for_user(self, user_id: int) -> SupportTicket | None:
        result = await self._session.execute(
            select(SupportTicket)
            .execution_options(populate_existing=True)
            .options(selectinload(SupportTicket.user))
            .where(SupportTicket.user_id == user_id)
            .where(SupportTicket.status == "open")
            .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int, *, limit: int = 10) -> list[SupportTicket]:
        result = await self._session.execute(
            select(SupportTicket)
            .execution_options(populate_existing=True)
            .options(
                selectinload(SupportTicket.user),
                selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
            )
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_by_status(self, status: str, *, limit: int = 20) -> list[SupportTicket]:
        result = await self._session.execute(
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.user),
                selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
            )
            .where(SupportTicket.status == status)
            .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def count_created_since(self, user_id: int, *, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count(SupportTicket.id))
            .where(SupportTicket.user_id == user_id)
            .where(SupportTicket.created_at >= since)
        )
        return int(result.scalar_one() or 0)

    async def count_by_status(self, status: str) -> int:
        result = await self._session.execute(
            select(func.count(SupportTicket.id)).where(SupportTicket.status == status)
        )
        return int(result.scalar_one() or 0)

    async def count_open_waiting_on_admin(self) -> int:
        result = await self._session.execute(
            select(func.count(SupportTicket.id))
            .where(SupportTicket.status == "open")
            .where(SupportTicket.last_user_message_at.is_not(None))
            .where(
                or_(
                    SupportTicket.last_admin_message_at.is_(None),
                    SupportTicket.last_user_message_at > SupportTicket.last_admin_message_at,
                )
            )
        )
        return int(result.scalar_one() or 0)

    async def count_open_waiting_on_user(self) -> int:
        result = await self._session.execute(
            select(func.count(SupportTicket.id))
            .where(SupportTicket.status == "open")
            .where(SupportTicket.last_admin_message_at.is_not(None))
            .where(
                or_(
                    SupportTicket.last_user_message_at.is_(None),
                    SupportTicket.last_admin_message_at >= SupportTicket.last_user_message_at,
                )
            )
        )
        return int(result.scalar_one() or 0)

    async def count_stale_open(self, *, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count(SupportTicket.id))
            .where(
                and_(
                    SupportTicket.status == "open",
                    SupportTicket.updated_at < since,
                )
            )
        )
        return int(result.scalar_one() or 0)

    async def set_status(
        self,
        ticket: SupportTicket,
        *,
        status: str,
        closed_at: datetime | None,
        closed_by_user_id: int | None,
        close_reason: str | None,
    ) -> SupportTicket:
        ticket.status = status
        ticket.closed_at = closed_at
        ticket.closed_by_user_id = closed_by_user_id
        ticket.close_reason = close_reason
        await self._session.flush()
        return ticket