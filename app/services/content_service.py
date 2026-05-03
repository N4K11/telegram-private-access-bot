from __future__ import annotations

import inspect
from dataclasses import dataclass
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.texts import render_text

CONTENT_MISSING_TEXT = (
    "📚 Материал пока недоступен.\n\n"
    "Попробуй открыть этот раздел позже или вернись в меню помощи."
)


@dataclass(frozen=True, slots=True)
class ContentEntry:
    slug: str
    template_key: str
    command: str | None
    button_text: str
    title: str
    summary: str


CONTENT_ENTRIES: tuple[ContentEntry, ...] = (
    ContentEntry(
        slug='faq',
        template_key='faq',
        command='faq',
        button_text='❔ FAQ',
        title='FAQ',
        summary='Частые вопросы о доступе, продлении и ссылках.',
    ),
    ContentEntry(
        slug='rules',
        template_key='channel_rules',
        command='rules',
        button_text='📜 Правила канала',
        title='Правила канала',
        summary='Правила поведения и причины возможного отзыва доступа.',
    ),
    ContentEntry(
        slug='after-payment',
        template_key='after_payment_guide',
        command='afterpay',
        button_text='✅ После оплаты',
        title='Инструкция после оплаты',
        summary='Что делать после покупки и как получить повторную ссылку.',
    ),
    ContentEntry(
        slug='crypto-payment',
        template_key='crypto_payment_guide',
        command='cryptopay',
        button_text='🪙 Crypto Pay',
        title='Инструкция по Crypto Pay',
        summary='Как проходит crypto-оплата и когда активируется доступ.',
    ),
    ContentEntry(
        slug='refunds',
        template_key='refund_policy',
        command=None,
        button_text='↩️ Возвраты',
        title='Политика возвратов',
        summary='Условия разбора ошибочных платежей и возвратов.',
    ),
    ContentEntry(
        slug='offer',
        template_key='offer',
        command='offer',
        button_text='📘 Оферта',
        title='Оферта',
        summary='Публичные условия покупки и использования подписки.',
    ),
)


def all_content_entries() -> tuple[ContentEntry, ...]:
    return CONTENT_ENTRIES


def get_content_entry(slug: str) -> ContentEntry | None:
    normalized = slug.strip().lower()
    for entry in CONTENT_ENTRIES:
        if entry.slug == normalized:
            return entry
    return None


def get_content_entry_by_command(command: str) -> ContentEntry | None:
    normalized = command.strip().lower()
    for entry in CONTENT_ENTRIES:
        if entry.command == normalized:
            return entry
    return None


async def render_content_text(
    session: AsyncSession | None,
    slug: str,
) -> str:
    entry = get_content_entry(slug)
    if entry is None:
        return CONTENT_MISSING_TEXT

    rendered = (
        render_text(session, entry.template_key)
        if session is not None
        else render_text(entry.template_key)
    )
    if inspect.isawaitable(rendered):
        rendered = await rendered
    return escape(str(rendered), quote=False)
