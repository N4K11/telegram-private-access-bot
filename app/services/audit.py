# ruff: noqa: E501
from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from io import StringIO
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repositories.audit_logs import AuditLogRepository
from app.db.repositories.users import UserRepository
from app.utils.datetime import ensure_aware_utc, format_datetime, utcnow

AuditPeriodKey = Literal["day", "week", "month", "all"]
PERIOD_DAY: AuditPeriodKey = "day"
PERIOD_WEEK: AuditPeriodKey = "week"
PERIOD_MONTH: AuditPeriodKey = "month"
PERIOD_ALL: AuditPeriodKey = "all"
AUDIT_PERIODS: tuple[AuditPeriodKey, ...] = (
    PERIOD_DAY,
    PERIOD_WEEK,
    PERIOD_MONTH,
    PERIOD_ALL,
)
PERIOD_LABELS: dict[AuditPeriodKey, str] = {
    PERIOD_DAY: "день",
    PERIOD_WEEK: "7 дней",
    PERIOD_MONTH: "30 дней",
    PERIOD_ALL: "всё время",
}
SENSITIVE_KEYWORDS = (
    "token",
    "secret",
    "password",
    "invite",
    "link",
    "url",
    "payload",
    "text",
    "body",
    "message",
    "notes",
)
BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
INVITE_LINK_RE = re.compile(r"https?://t\.me/(?:joinchat/|\+)[A-Za-z0-9_-]+", re.IGNORECASE)
ACTION_FILTER_MAX_LENGTH = 128
DEFAULT_AUDIT_PAGE_SIZE = 4
DEFAULT_AUDIT_EXPORT_LIMIT = 1000


class AuditViewerError(ValueError):
    """Raised when audit viewer input is invalid."""


@dataclass(slots=True, frozen=True)
class AuditViewerFilters:
    target_user_id: int | None = None
    actor_user_id: int | None = None
    action: str | None = None
    period: AuditPeriodKey = PERIOD_ALL


@dataclass(slots=True)
class AuditUserReference:
    user_id: int
    telegram_id: int | None
    display_name: str


@dataclass(slots=True)
class AuditEventSummary:
    id: int
    action: str
    created_at: datetime
    actor: AuditUserReference | None
    target: AuditUserReference | None
    payload_preview: str | None


@dataclass(slots=True)
class AuditEventDetail:
    id: int
    action: str
    created_at: datetime
    actor: AuditUserReference | None
    target: AuditUserReference | None
    payload_redacted: str | None


@dataclass(slots=True)
class AuditPage:
    filters: AuditViewerFilters
    filter_target: AuditUserReference | None
    filter_actor: AuditUserReference | None
    items: list[AuditEventSummary]
    page: int
    total_pages: int
    total_items: int
    available_actions: list[str]


@dataclass(slots=True)
class AuditCsvReport:
    data: bytes
    row_count: int
    total_count: int

    @property
    def is_truncated(self) -> bool:
        return self.row_count < self.total_count


async def write_audit_log(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: int | None = None,
    target_user_id: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> None:
    serialized_payload = None
    if payload:
        serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    await AuditLogRepository(session).create(
        action=action,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        payload=serialized_payload,
    )


async def build_audit_page(
    session: AsyncSession,
    *,
    filters: AuditViewerFilters,
    page: int = 1,
    page_size: int = DEFAULT_AUDIT_PAGE_SIZE,
    now: datetime | None = None,
) -> AuditPage:
    current_time = ensure_aware_utc(now or utcnow())
    repository = AuditLogRepository(session)
    created_since = _period_start(filters.period, current_time)
    total_items = await repository.count_filtered(
        actor_user_id=filters.actor_user_id,
        target_user_id=filters.target_user_id,
        action=filters.action,
        created_since=created_since,
    )
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    normalized_page = min(max(page, 1), total_pages)
    records = await repository.list_filtered(
        actor_user_id=filters.actor_user_id,
        target_user_id=filters.target_user_id,
        action=filters.action,
        created_since=created_since,
        limit=page_size,
        offset=(normalized_page - 1) * page_size,
    )

    user_map = await _load_user_map(session, _collect_user_ids(records, filters))
    items = [
        AuditEventSummary(
            id=record.id,
            action=record.action,
            created_at=ensure_aware_utc(record.created_at),
            actor=_build_user_reference(record.actor_user_id, user_map),
            target=_build_user_reference(record.target_user_id, user_map),
            payload_preview=preview_redacted_audit_payload(record.payload),
        )
        for record in records
    ]

    return AuditPage(
        filters=filters,
        filter_target=_build_user_reference(filters.target_user_id, user_map),
        filter_actor=_build_user_reference(filters.actor_user_id, user_map),
        items=items,
        page=normalized_page,
        total_pages=total_pages,
        total_items=total_items,
        available_actions=await repository.list_distinct_actions(limit=8),
    )


async def get_audit_event_detail(
    session: AsyncSession,
    *,
    audit_log_id: int,
) -> AuditEventDetail:
    record = await AuditLogRepository(session).get_by_id(audit_log_id)
    if record is None:
        raise AuditViewerError("Событие аудита не найдено.")

    user_map = await _load_user_map(
        session,
        {
            user_id
            for user_id in (record.actor_user_id, record.target_user_id)
            if user_id is not None
        },
    )
    return AuditEventDetail(
        id=record.id,
        action=record.action,
        created_at=ensure_aware_utc(record.created_at),
        actor=_build_user_reference(record.actor_user_id, user_map),
        target=_build_user_reference(record.target_user_id, user_map),
        payload_redacted=serialize_redacted_audit_payload(record.payload),
    )


async def build_audit_csv_report(
    session: AsyncSession,
    *,
    filters: AuditViewerFilters,
    timezone: str,
    now: datetime | None = None,
    limit: int = DEFAULT_AUDIT_EXPORT_LIMIT,
) -> AuditCsvReport:
    current_time = ensure_aware_utc(now or utcnow())
    repository = AuditLogRepository(session)
    created_since = _period_start(filters.period, current_time)
    total_items = await repository.count_filtered(
        actor_user_id=filters.actor_user_id,
        target_user_id=filters.target_user_id,
        action=filters.action,
        created_since=created_since,
    )
    records = await repository.list_filtered(
        actor_user_id=filters.actor_user_id,
        target_user_id=filters.target_user_id,
        action=filters.action,
        created_since=created_since,
        limit=limit,
        offset=0,
    )
    user_map = await _load_user_map(session, _collect_user_ids(records, filters))

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "audit_log_id",
            "created_at",
            "action",
            "actor_user_id",
            "actor_telegram_id",
            "actor_name",
            "target_user_id",
            "target_telegram_id",
            "target_name",
            "payload_redacted",
        ]
    )
    for record in records:
        actor = _build_user_reference(record.actor_user_id, user_map)
        target = _build_user_reference(record.target_user_id, user_map)
        writer.writerow(
            [
                record.id,
                format_datetime(ensure_aware_utc(record.created_at), timezone),
                record.action,
                actor.user_id if actor is not None else "",
                actor.telegram_id if actor is not None else "",
                actor.display_name if actor is not None else "",
                target.user_id if target is not None else "",
                target.telegram_id if target is not None else "",
                target.display_name if target is not None else "",
                serialize_redacted_audit_payload(record.payload) or "",
            ]
        )

    return AuditCsvReport(
        data=buffer.getvalue().encode("utf-8"),
        row_count=len(records),
        total_count=total_items,
    )


async def resolve_audit_user_reference(
    session: AsyncSession,
    raw_value: str,
) -> AuditUserReference:
    normalized = raw_value.strip()
    if not normalized:
        raise AuditViewerError("Нужно указать ID пользователя.")

    repository = UserRepository(session)
    user: User | None = None
    if normalized.lower().startswith("tg:"):
        telegram_id = _parse_positive_int(normalized[3:])
        user = await repository.get_by_telegram_id(telegram_id)
    elif normalized.lower().startswith("id:"):
        user_id = _parse_positive_int(normalized[3:])
        user = await repository.get_by_id(user_id)
    else:
        numeric_value = _parse_positive_int(normalized)
        user = await repository.get_by_id(numeric_value)
        if user is None:
            user = await repository.get_by_telegram_id(numeric_value)

    if user is None:
        raise AuditViewerError("Пользователь по этому ID не найден.")
    return AuditUserReference(
        user_id=user.id,
        telegram_id=user.telegram_id,
        display_name=_format_user_display_name(user),
    )


def normalize_audit_period(value: str | AuditPeriodKey) -> AuditPeriodKey:
    normalized = str(value).strip().lower()
    if normalized not in AUDIT_PERIODS:
        raise AuditViewerError("Неизвестный период фильтра.")
    return normalized  # type: ignore[return-value]


def normalize_audit_action_filter(raw_value: str) -> str | None:
    normalized = raw_value.strip()
    if not normalized or normalized in {"-", "*"} or normalized.lower() == "all":
        return None
    if len(normalized) > ACTION_FILTER_MAX_LENGTH:
        raise AuditViewerError(
            f"Имя действия слишком длинное. Максимум: {ACTION_FILTER_MAX_LENGTH} символов."
        )
    if any(char.isspace() for char in normalized):
        raise AuditViewerError("Имя действия должно быть без пробелов. Например: payment_paid_stars")
    return normalized


async def list_recent_audit_actions(session: AsyncSession, *, limit: int = 8) -> list[str]:
    return await AuditLogRepository(session).list_distinct_actions(limit=limit)


def build_audit_report_filename(*, generated_at: datetime) -> str:
    timestamp = ensure_aware_utc(generated_at).strftime("%Y%m%d-%H%M%S")
    return f"audit-report-{timestamp}.csv"


def render_audit_overview(page: AuditPage, *, timezone: str) -> str:
    lines = [
        "📜 Аудит действий",
        "",
        "Фильтры:",
        f"• Период: {PERIOD_LABELS[page.filters.period]}",
        f"• Цель: {_format_filter_reference(page.filter_target)}",
        f"• Актор: {_format_filter_reference(page.filter_actor)}",
        f"• Действие: {escape(page.filters.action) if page.filters.action else 'все'}",
        "",
    ]
    if not page.items:
        lines.append("По текущим фильтрам событий нет.")
    else:
        for item in page.items:
            lines.append(
                f"#{item.id} • {format_datetime(item.created_at, timezone)} • {escape(item.action)}"
            )
            lines.append(f"Актор: {_format_filter_reference(item.actor)}")
            lines.append(f"Цель: {_format_filter_reference(item.target)}")
            if item.payload_preview:
                lines.append(f"Payload: {escape(item.payload_preview)}")
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    lines.extend(
        [
            "",
            f"Страница {page.page}/{page.total_pages} • Всего событий: {page.total_items}",
        ]
    )
    if page.available_actions:
        lines.append(
            "Примеры действий: " + ", ".join(escape(action) for action in page.available_actions)
        )
    return "\n".join(lines)


def render_audit_event_detail(detail: AuditEventDetail, *, timezone: str) -> str:
    lines = [
        f"📜 Событие аудита #{detail.id}",
        "",
        f"Время: {format_datetime(detail.created_at, timezone)}",
        f"Действие: {escape(detail.action)}",
        f"Актор: {_format_filter_reference(detail.actor)}",
        f"Цель: {_format_filter_reference(detail.target)}",
    ]
    if detail.payload_redacted:
        lines.extend(["", "Payload:", escape(detail.payload_redacted)])
    else:
        lines.extend(["", "Payload: —"])
    return "\n".join(lines)


def preview_redacted_audit_payload(raw_payload: str | None) -> str | None:
    payload = redact_audit_payload(raw_payload)
    if payload is None:
        return None
    if isinstance(payload, dict):
        chunks = [f"{key}={_preview_value(value)}" for key, value in sorted(payload.items())]
        preview = ", ".join(chunks)
    elif isinstance(payload, list):
        preview = ", ".join(_preview_value(item) for item in payload)
    else:
        preview = _preview_value(payload)
    preview = " ".join(str(preview).split())
    if len(preview) <= 90:
        return preview
    return f"{preview[:87]}..."


def serialize_redacted_audit_payload(raw_payload: str | None) -> str | None:
    payload = redact_audit_payload(raw_payload)
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    return str(payload)


def redact_audit_payload(raw_payload: str | None) -> Any | None:
    if not raw_payload:
        return None
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return _redact_string(raw_payload)
    return _redact_value(decoded)


def _redact_value(value: Any, key_hint: str | None = None) -> Any:
    if key_hint is not None and _is_sensitive_key(key_hint):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(key): _redact_value(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _redact_string(value: str) -> str:
    if BOT_TOKEN_RE.search(value) or INVITE_LINK_RE.search(value):
        return "[REDACTED]"
    collapsed = " ".join(value.split())
    if len(collapsed) <= 220:
        return collapsed
    return f"{collapsed[:217]}..."


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEYWORDS)


def _preview_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_preview_value(item) for item in value[:3]) + ("]" if len(value) <= 3 else ", ...]")
    if isinstance(value, dict):
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return _redact_string(serialized)
    return str(value)


def _period_start(period: AuditPeriodKey, now: datetime) -> datetime | None:
    if period == PERIOD_ALL:
        return None
    if period == PERIOD_DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == PERIOD_WEEK:
        return now - timedelta(days=7)
    return now - timedelta(days=30)


def _collect_user_ids(records, filters: AuditViewerFilters) -> set[int]:
    user_ids: set[int] = set()
    for record in records:
        if record.actor_user_id is not None:
            user_ids.add(record.actor_user_id)
        if record.target_user_id is not None:
            user_ids.add(record.target_user_id)
    if filters.actor_user_id is not None:
        user_ids.add(filters.actor_user_id)
    if filters.target_user_id is not None:
        user_ids.add(filters.target_user_id)
    return user_ids


async def _load_user_map(session: AsyncSession, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    result = await session.execute(select(User).where(User.id.in_(sorted(user_ids))))
    return {user.id: user for user in result.scalars()}


def _build_user_reference(
    user_id: int | None,
    user_map: dict[int, User],
) -> AuditUserReference | None:
    if user_id is None:
        return None
    user = user_map.get(user_id)
    if user is None:
        return AuditUserReference(
            user_id=user_id,
            telegram_id=None,
            display_name=f"Пользователь #{user_id}",
        )
    return AuditUserReference(
        user_id=user.id,
        telegram_id=user.telegram_id,
        display_name=_format_user_display_name(user),
    )


def _format_user_display_name(user: User) -> str:
    parts = [part.strip() for part in (user.first_name or "", user.last_name or "") if part and part.strip()]
    if parts:
        return " ".join(parts)
    if user.username:
        return f"@{user.username}"
    return f"Пользователь #{user.id}"


def _format_filter_reference(reference: AuditUserReference | None) -> str:
    if reference is None:
        return "все"
    if reference.telegram_id is None:
        return escape(reference.display_name)
    return f"{escape(reference.display_name)} (id {reference.user_id} / tg {reference.telegram_id})"


def _parse_positive_int(raw_value: str) -> int:
    try:
        value = int(raw_value.strip())
    except ValueError as exc:
        raise AuditViewerError("ID должен быть числом.") from exc
    if value <= 0:
        raise AuditViewerError("ID должен быть положительным числом.")
    return value



