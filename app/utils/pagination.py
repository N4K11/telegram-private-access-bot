from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Page:
    items: list[object]
    page: int
    per_page: int
    total: int
