from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

from app.config import Settings

RATE_LIMIT_MESSAGE = "Too many requests. Please slow down."
DUPLICATE_MESSAGE = "Duplicate requests are temporarily limited."


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        window_seconds: int,
        max_events: int,
        duplicate_window_seconds: int,
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = max(1, window_seconds)
        self._max_events = max(1, max_events)
        self._duplicate_window_seconds = max(1, duplicate_window_seconds)
        self._time_func = time_func
        self._events: dict[tuple[int, str], deque[float]] = {}
        self._duplicates: dict[tuple[int, str], tuple[str, float]] = {}
        self._notice_times: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event)
        if user_id is None:
            return await handler(event, data)

        settings = data.get("settings")
        if isinstance(settings, Settings) and user_id in settings.admin_ids_set:
            return await handler(event, data)

        event_kind = type(event).__name__
        now = self._time_func()

        text = _extract_event_text(event)
        if text and self._is_duplicate(user_id, event_kind, text, now):
            await self._notify(event, user_id, event_kind, DUPLICATE_MESSAGE, now)
            return None

        if self._is_rate_limited(user_id, event_kind, now):
            await self._notify(event, user_id, event_kind, RATE_LIMIT_MESSAGE, now)
            return None

        return await handler(event, data)

    def _is_rate_limited(self, user_id: int, event_kind: str, now: float) -> bool:
        key = (user_id, event_kind)
        events = self._events.setdefault(key, deque())
        while events and now - events[0] > self._window_seconds:
            events.popleft()
        if len(events) >= self._max_events:
            return True
        events.append(now)
        return False

    def _is_duplicate(self, user_id: int, event_kind: str, text: str, now: float) -> bool:
        key = (user_id, event_kind)
        previous = self._duplicates.get(key)
        self._duplicates[key] = (text, now)
        if previous is None:
            return False
        previous_text, previous_time = previous
        return previous_text == text and now - previous_time <= self._duplicate_window_seconds

    async def _notify(
        self,
        event: Any,
        user_id: int,
        event_kind: str,
        message: str,
        now: float,
    ) -> None:
        notice_key = (user_id, event_kind)
        previous_notice_time = self._notice_times.get(notice_key)
        if previous_notice_time is not None and now - previous_notice_time < 1.0:
            return
        self._notice_times[notice_key] = now

        if hasattr(event, "invoice_payload"):
            await event.answer(ok=False, error_message=message)
            return
        await event.answer(message)


def _extract_user_id(event: Any) -> int | None:
    user = getattr(event, "from_user", None)
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def _extract_event_text(event: Any) -> str | None:
    if hasattr(event, "invoice_payload"):
        return (getattr(event, "invoice_payload", "") or "").strip() or None
    if hasattr(event, "data"):
        return (getattr(event, "data", "") or "").strip() or None
    return (
        getattr(event, "text", None)
        or getattr(event, "caption", None)
        or ""
    ).strip() or None