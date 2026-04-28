from __future__ import annotations


def pluralize(value: int, singular: str, plural: str) -> str:
    return singular if value == 1 else plural
