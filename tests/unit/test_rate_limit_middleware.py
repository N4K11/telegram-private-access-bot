from __future__ import annotations

from app.bot.middlewares.rate_limit import (
    DUPLICATE_MESSAGE,
    RATE_LIMIT_MESSAGE,
    RateLimitMiddleware,
)
from app.config import Settings


class DummyUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class DummyMessage:
    def __init__(self, user_id: int, text: str) -> None:
        self.from_user = DummyUser(user_id)
        self.text = text
        self.answer_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_calls.append((args, kwargs))


class DummyPreCheckout:
    def __init__(self, user_id: int, invoice_payload: str) -> None:
        self.from_user = DummyUser(user_id)
        self.invoice_payload = invoice_payload
        self.answer_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answer_calls.append((args, kwargs))


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


async def test_rate_limit_blocks_excessive_messages() -> None:
    clock = Clock()
    middleware = RateLimitMiddleware(
        window_seconds=5,
        max_events=2,
        duplicate_window_seconds=10,
        time_func=clock,
    )
    calls: list[str] = []

    async def handler(event, _data):
        calls.append(event.text)
        return "ok"

    first = DummyMessage(42, "one")
    second = DummyMessage(42, "two")
    third = DummyMessage(42, "three")

    assert await middleware(handler, first, {}) == "ok"
    assert await middleware(handler, second, {}) == "ok"
    assert await middleware(handler, third, {}) is None
    assert calls == ["one", "two"]
    assert third.answer_calls[0][0] == (RATE_LIMIT_MESSAGE,)


async def test_duplicate_messages_are_blocked_temporarily() -> None:
    clock = Clock()
    middleware = RateLimitMiddleware(
        window_seconds=5,
        max_events=5,
        duplicate_window_seconds=10,
        time_func=clock,
    )
    calls: list[str] = []

    async def handler(event, _data):
        calls.append(event.text)
        return "ok"

    first = DummyMessage(7, "hello")
    second = DummyMessage(7, "hello")

    assert await middleware(handler, first, {}) == "ok"
    assert await middleware(handler, second, {}) is None
    assert calls == ["hello"]
    assert second.answer_calls[0][0] == (DUPLICATE_MESSAGE,)


async def test_admins_bypass_rate_limit() -> None:
    clock = Clock()
    middleware = RateLimitMiddleware(
        window_seconds=5,
        max_events=1,
        duplicate_window_seconds=10,
        time_func=clock,
    )
    settings = Settings.model_validate({"bot_token": "123:token", "admin_ids": [55]})
    calls = 0

    async def handler(_event, _data):
        nonlocal calls
        calls += 1
        return "ok"

    first = DummyMessage(55, "same")
    second = DummyMessage(55, "same")

    assert await middleware(handler, first, {"settings": settings}) == "ok"
    assert await middleware(handler, second, {"settings": settings}) == "ok"
    assert calls == 2


async def test_pre_checkout_rejection_uses_query_error_payload() -> None:
    clock = Clock()
    middleware = RateLimitMiddleware(
        window_seconds=5,
        max_events=1,
        duplicate_window_seconds=10,
        time_func=clock,
    )

    async def handler(_event, _data):
        return "ok"

    first = DummyPreCheckout(11, "payload-1")
    second = DummyPreCheckout(11, "payload-2")

    assert await middleware(handler, first, {}) == "ok"
    assert await middleware(handler, second, {}) is None
    assert second.answer_calls[0][1] == {"ok": False, "error_message": RATE_LIMIT_MESSAGE}