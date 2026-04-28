from __future__ import annotations


def contains_mojibake(text: str) -> bool:
    bad_fragments = ("Рџ", "Ð", "Ñ", "�")
    return any(fragment in text for fragment in bad_fragments)
