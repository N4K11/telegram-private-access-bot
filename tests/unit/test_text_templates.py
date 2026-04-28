from app.services.texts import DEFAULT_TEXT_TEMPLATES, has_mojibake


def test_default_text_templates_are_clean_and_keep_emoji() -> None:
    values = []
    for template in DEFAULT_TEXT_TEMPLATES.values():
        values.extend([template.title, template.body])

    assert values
    assert all(not has_mojibake(value) for value in values)
    assert DEFAULT_TEXT_TEMPLATES["admin_menu_texts"].body == "✍️ Тексты"
    assert "Здравствуйте" in DEFAULT_TEXT_TEMPLATES["start"].body