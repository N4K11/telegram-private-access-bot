# ruff: noqa: E501
from __future__ import annotations

import shutil
from pathlib import Path

from app.tools.text_repair import repair_file, scan_default_template_issues, scan_file
from app.utils.encoding import repair_mojibake_text, safe_ui_text


def _to_mojibake(value: str) -> str:
    return value.encode("utf-8").decode("cp1251")


def test_repair_mojibake_text_restores_expected_value() -> None:
    broken = _to_mojibake("\u041d\u0430\u0437\u0430\u0434")
    assert repair_mojibake_text(broken) == "\u041d\u0430\u0437\u0430\u0434"


def test_safe_ui_text_uses_fallback_for_mojibake() -> None:
    broken = _to_mojibake("\u041d\u0430\u0437\u0430\u0434")
    assert safe_ui_text(broken, "fallback") == "fallback"


def test_scan_default_template_issues_is_clean() -> None:
    assert scan_default_template_issues() == []


def test_repair_file_repairs_detected_lines() -> None:
    workspace_tmp = Path("tests/.tmp_text_repair")
    if workspace_tmp.exists():
        shutil.rmtree(workspace_tmp)
    workspace_tmp.mkdir(parents=True)

    try:
        broken_line = _to_mojibake("\u041a\u043d\u043e\u043f\u043a\u0430 \u041d\u0430\u0437\u0430\u0434")
        path = workspace_tmp / "sample.txt"
        path.write_text(f"header\n{broken_line}\n", encoding="utf-8")

        issues = scan_file(path)
        assert len(issues) == 1
        assert issues[0].repaired == "\u041a\u043d\u043e\u043f\u043a\u0430 \u041d\u0430\u0437\u0430\u0434"

        changed = repair_file(path)
        assert changed == 1
        assert path.read_text(encoding="utf-8").splitlines() == ["header", "\u041a\u043d\u043e\u043f\u043a\u0430 \u041d\u0430\u0437\u0430\u0434"]
    finally:
        if workspace_tmp.exists():
            shutil.rmtree(workspace_tmp)
