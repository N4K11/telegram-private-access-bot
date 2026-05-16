from __future__ import annotations

ADMIN_DETAIL_DEFAULT_LIMIT = 10
ADMIN_DETAIL_MAX_LIMIT = 50
ADMIN_PAGE_DEFAULT_SIZE = 8
ADMIN_PAGE_MAX_SIZE = 50
ADMIN_PREVIEW_LIMIT = 4


def clamp_admin_detail_limit(
    value: int | None,
    *,
    default: int = ADMIN_DETAIL_DEFAULT_LIMIT,
) -> int:
    raw = default if value is None else int(value)
    return max(1, min(raw, ADMIN_DETAIL_MAX_LIMIT))


def clamp_admin_page_size(
    value: int | None,
    *,
    default: int = ADMIN_PAGE_DEFAULT_SIZE,
) -> int:
    raw = default if value is None else int(value)
    return max(1, min(raw, ADMIN_PAGE_MAX_SIZE))
