from __future__ import annotations

from app.services.legal_texts import (
    all_legal_text_entries,
    get_legal_text_entry,
    get_legal_text_entry_by_command,
)
from app.services.texts import DEFAULT_TEXT_TEMPLATES


def test_legal_text_entries_map_to_managed_templates() -> None:
    entries = all_legal_text_entries()

    assert [entry.slug for entry in entries] == [
        "payment-support",
        "terms",
        "privacy",
        "refunds",
    ]
    assert get_legal_text_entry("terms") is not None
    assert get_legal_text_entry_by_command("paysupport") is not None
    assert get_legal_text_entry_by_command("paysupport").template_key == "payment_support"
    assert get_legal_text_entry_by_command("refunds").template_key == "refund_policy"
    assert all(entry.template_key in DEFAULT_TEXT_TEMPLATES for entry in entries)
