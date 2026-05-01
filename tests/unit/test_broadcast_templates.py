from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import create_async_engine, create_session_factory
from app.services.broadcasts import (
    get_broadcast_template,
    list_broadcast_templates,
    save_broadcast_template,
)


async def _create_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    session = session_factory()
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


async def _close_session(session: AsyncSession) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    await session.close()
    await engine.dispose()


async def test_save_and_list_broadcast_templates_updates_existing() -> None:
    session = await _create_session()
    try:
        first = await save_broadcast_template(
            session,
            title="Retention 1",
            content="Hello all",
            updated_by_user_id=1,
        )
        await session.commit()

        second = await save_broadcast_template(
            session,
            title="Retention 1",
            content="Updated body",
            updated_by_user_id=2,
        )
        await session.commit()

        templates = await list_broadcast_templates(session)
        loaded = await get_broadcast_template(session, key=first.key)

        assert first.key == second.key
        assert len(templates) == 1
        assert templates[0].title == "Retention 1"
        assert templates[0].content == "Updated body"
        assert loaded is not None
        assert loaded.content == "Updated body"
    finally:
        await _close_session(session)

