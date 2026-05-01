from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LegalTextEntry:
    slug: str
    template_key: str
    command: str | None
    button_text: str
    title: str


LEGAL_TEXT_ENTRIES: tuple[LegalTextEntry, ...] = (
    LegalTextEntry(
        slug="payment-support",
        template_key="payment_support",
        command="paysupport",
        button_text="💳 Помощь с оплатой",
        title="Поддержка оплаты",
    ),
    LegalTextEntry(
        slug="terms",
        template_key="terms",
        command="terms",
        button_text="📄 Условия",
        title="Условия использования",
    ),
    LegalTextEntry(
        slug="privacy",
        template_key="privacy",
        command="privacy",
        button_text="🔒 Конфиденциальность",
        title="Политика конфиденциальности",
    ),
    LegalTextEntry(
        slug="refunds",
        template_key="refund_policy",
        command="refunds",
        button_text="↩️ Возвраты",
        title="Политика возвратов",
    ),
)


def all_legal_text_entries() -> tuple[LegalTextEntry, ...]:
    return LEGAL_TEXT_ENTRIES


def get_legal_text_entry(slug: str) -> LegalTextEntry | None:
    normalized = slug.strip().lower()
    for entry in LEGAL_TEXT_ENTRIES:
        if entry.slug == normalized:
            return entry
    return None


def get_legal_text_entry_by_command(command: str) -> LegalTextEntry | None:
    normalized = command.strip().lower()
    for entry in LEGAL_TEXT_ENTRIES:
        if entry.command == normalized:
            return entry
    return None