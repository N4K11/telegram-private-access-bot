from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import TextTemplate
from app.db.session import create_async_engine, create_session_factory
from app.services.content_service import (
    CONTENT_MISSING_TEXT,
    all_content_entries,
    get_content_entry,
    get_content_entry_by_command,
    render_content_text,
)
from app.services.texts import ensure_default_text_templates


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_content_registry_exposes_expected_entries() -> None:
    slugs = {entry.slug for entry in all_content_entries()}
    assert {'faq', 'rules', 'after-payment', 'crypto-payment', 'refunds', 'offer'} == slugs
    assert get_content_entry('faq') is not None
    assert get_content_entry_by_command('offer').template_key == 'offer'
    assert get_content_entry_by_command('cryptopay').template_key == 'crypto_payment_guide'


async def test_render_content_text_uses_managed_template_and_escapes_html(
    session: AsyncSession,
) -> None:
    await ensure_default_text_templates(session)
    template = await session.scalar(select(TextTemplate).where(TextTemplate.key == 'faq'))
    assert template is not None
    template.body = '<b>FAQ</b> & <i>rules</i>'
    await session.commit()

    rendered = await render_content_text(session, 'faq')

    assert rendered == '&lt;b&gt;FAQ&lt;/b&gt; &amp; &lt;i&gt;rules&lt;/i&gt;'


async def test_render_content_text_returns_missing_fallback() -> None:
    rendered = await render_content_text(None, 'missing-slug')
    assert rendered == CONTENT_MISSING_TEXT
