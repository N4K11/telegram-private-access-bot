# ruff: noqa: E501
from app.services.texts import DEFAULT_TEXT_TEMPLATES, has_mojibake


def test_default_text_templates_are_clean_and_keep_emoji() -> None:
    values = []
    for template in DEFAULT_TEXT_TEMPLATES.values():
        values.extend([template.title, template.body])

    assert values
    assert all(not has_mojibake(value) for value in values)
    assert DEFAULT_TEXT_TEMPLATES["admin_menu_texts"].body == "\u270d\ufe0f \u0422\u0435\u043a\u0441\u0442\u044b"
    assert "\u041f\u0440\u0438\u0432\u0435\u0442" in DEFAULT_TEXT_TEMPLATES["start"].body
