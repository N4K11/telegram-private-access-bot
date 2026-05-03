from __future__ import annotations

from collections.abc import Iterable

MOJIBAKE_FRAGMENTS: tuple[str, ...] = (
    "Р Сџ",
    "Р Сњ",
    "Р В°",
    "Р РЋ",
    "Р вЂњ",
    "Р С™",
    "Гђ",
    "Г‘",
    "PIPS",
    "PjP",
    "PВ¤",
    "PвЂў",
    "пїЅ",
    "РІВ­С’",
    "РІвЂљС—",
    "СЂСџ",
    "Рџ",
    "РЎ",
    "Рќ",
    "Рђ",
    "Рљ",
    "Рў",
    "рџ",
    "вЂ",
)


def is_mojibake(text: str | None) -> bool:
    if text is None:
        return False
    normalized = str(text)
    return any(fragment in normalized for fragment in MOJIBAKE_FRAGMENTS)


def contains_mojibake(text: str) -> bool:
    return is_mojibake(text)


def repair_mojibake_text(text: str | None) -> str | None:
    if text is None:
        return None

    candidate = str(text)
    if not is_mojibake(candidate):
        return candidate

    repaired = candidate
    for _ in range(3):
        try:
            next_value = repaired.encode("cp1251").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if not next_value or next_value == repaired:
            break
        repaired = next_value
        if not is_mojibake(repaired):
            break

    return repaired or candidate


def safe_ui_text(text: str | None, fallback: str) -> str:
    candidate = (text or "").strip()
    if not candidate or is_mojibake(candidate):
        return fallback
    return candidate


def find_mojibake_values(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(label, value) for label, value in items if is_mojibake(value)]