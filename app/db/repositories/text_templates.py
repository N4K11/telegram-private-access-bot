from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TextTemplate


class TextTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[TextTemplate]:
        result = await self._session.execute(
            select(TextTemplate).order_by(TextTemplate.title.asc(), TextTemplate.key.asc())
        )
        return list(result.scalars())

    async def get_by_key(self, key: str) -> TextTemplate | None:
        result = await self._session.execute(
            select(TextTemplate).where(TextTemplate.key == key)
        )
        return result.scalar_one_or_none()

    async def get_by_keys(self, keys: Sequence[str]) -> dict[str, TextTemplate]:
        normalized_keys = tuple(dict.fromkeys(keys))
        if not normalized_keys:
            return {}

        result = await self._session.execute(
            select(TextTemplate).where(TextTemplate.key.in_(normalized_keys))
        )
        templates = list(result.scalars())
        return {template.key: template for template in templates}

    async def create(
        self,
        *,
        key: str,
        title: str,
        body: str,
        is_system: bool,
        updated_by_user_id: int | None = None,
    ) -> TextTemplate:
        template = TextTemplate(
            key=key,
            title=title,
            body=body,
            is_system=is_system,
            updated_by_user_id=updated_by_user_id,
        )
        self._session.add(template)
        await self._session.flush()
        return template