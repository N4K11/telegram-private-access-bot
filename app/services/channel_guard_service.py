# ruff: noqa: E501
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from html import escape

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel
from app.db.repositories.channels import ChannelRepository
from app.services.channel_diagnostics import build_channel_diagnostics_report
from app.services.observability import EVENT_CHANNEL_GUARD_INCIDENT

logger = logging.getLogger(__name__)

_last_alert_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class ChannelGuardIssue:
    channel_id: int
    title: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ChannelGuardResult:
    checked_channel_count: int
    issues: tuple[ChannelGuardIssue, ...]
    notified_admin_ids: tuple[int, ...] = ()
    alert_text: str | None = None
    suppressed: bool = False
    get_me_error: str | None = None

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @property
    def alert_sent(self) -> bool:
        return bool(self.notified_admin_ids)


ISSUE_MESSAGES: dict[str, str] = {
    "channel_unavailable": "Канал недоступен через Telegram API.",
    "membership_check_failed": "Не удалось проверить статус бота в канале.",
    "bot_kicked": "Бот больше не состоит в канале.",
    "not_admin": "Бот не администратор.",
    "no_invite_permission": "Нет права создавать invite links.",
    "no_restrict_permission": "Нет права restrict/ban пользователей.",
}


def reset_channel_guard_state() -> None:
    global _last_alert_fingerprint
    _last_alert_fingerprint = None


async def run_channel_guard(
    *,
    bot: Bot,
    channels: list[Channel],
    admin_ids: set[int] | list[int] | tuple[int, ...],
) -> ChannelGuardResult:
    global _last_alert_fingerprint

    active_channels = [channel for channel in channels if channel.is_active]
    if not active_channels:
        _last_alert_fingerprint = None
        return ChannelGuardResult(checked_channel_count=0, issues=())

    report = await build_channel_diagnostics_report(bot, active_channels)
    issues = _extract_guard_issues(report)
    fingerprint = _issues_fingerprint(issues)

    if not issues:
        _last_alert_fingerprint = None
        return ChannelGuardResult(
            checked_channel_count=len(active_channels),
            issues=(),
            get_me_error=report.get_me_error,
        )

    if fingerprint == _last_alert_fingerprint:
        return ChannelGuardResult(
            checked_channel_count=len(active_channels),
            issues=issues,
            alert_text=render_channel_guard_alert(issues),
            suppressed=True,
            get_me_error=report.get_me_error,
        )

    alert_text = render_channel_guard_alert(issues)
    channel_count = len({issue.channel_id for issue in issues})
    logger.error(
        "Channel guard detected issues in %s channels.",
        channel_count,
        extra={
            "event_name": EVENT_CHANNEL_GUARD_INCIDENT,
            "channel_count": channel_count,
            "issue_count": len(issues),
        },
    )

    notified_admin_ids: list[int] = []
    for admin_id in sorted(set(admin_ids)):
        try:
            await bot.send_message(admin_id, alert_text)
            notified_admin_ids.append(admin_id)
        except Exception:
            logger.exception("Failed to deliver channel guard alert to admin %s", admin_id)

    if notified_admin_ids:
        _last_alert_fingerprint = fingerprint

    return ChannelGuardResult(
        checked_channel_count=len(active_channels),
        issues=issues,
        notified_admin_ids=tuple(notified_admin_ids),
        alert_text=alert_text,
        suppressed=not notified_admin_ids and fingerprint == _last_alert_fingerprint,
        get_me_error=report.get_me_error,
    )


async def run_channel_guard_cycle(
    *,
    session: AsyncSession,
    bot: Bot,
    admin_ids: set[int] | list[int] | tuple[int, ...],
) -> ChannelGuardResult:
    channels = await ChannelRepository(session).list_active()
    return await run_channel_guard(bot=bot, channels=channels, admin_ids=admin_ids)


def render_channel_guard_alert(issues: tuple[ChannelGuardIssue, ...]) -> str:
    grouped: dict[tuple[int, str], list[ChannelGuardIssue]] = defaultdict(list)
    for issue in issues:
        grouped[(issue.channel_id, issue.title)].append(issue)

    lines = ["🚨 Бот потерял права в канале", ""]
    for (_channel_id, title), channel_issues in grouped.items():
        lines.append(f"📣 {escape(title)}")
        for issue in channel_issues:
            lines.append(f"• {escape(issue.message)}")
        lines.append("")

    lines.append("Invite links и revoke могут не работать.")
    lines.append("Проверьте /admin_channel_check.")
    return "\n".join(lines)


def _extract_guard_issues(report) -> tuple[ChannelGuardIssue, ...]:
    issues: list[ChannelGuardIssue] = []
    for result in report.results:
        failed = {check.label: check for check in result.checks if not check.ok}
        if "Канал доступен через Telegram API" in failed:
            issues.append(_issue(result, "channel_unavailable"))
        if "Статус бота в канале" in failed:
            issues.append(_issue(result, "membership_check_failed"))
        if "Бот состоит в канале" in failed:
            issues.append(_issue(result, "bot_kicked"))
        if "Бот администратор" in failed:
            issues.append(_issue(result, "not_admin"))
        if "Может создавать invite links" in failed:
            issues.append(_issue(result, "no_invite_permission"))
        if "Может ограничивать пользователей" in failed:
            issues.append(_issue(result, "no_restrict_permission"))
    return tuple(issues)


def _issue(result, code: str) -> ChannelGuardIssue:
    return ChannelGuardIssue(
        channel_id=result.channel_id,
        title=result.title,
        code=code,
        message=ISSUE_MESSAGES[code],
    )


def _issues_fingerprint(issues: tuple[ChannelGuardIssue, ...]) -> str | None:
    if not issues:
        return None
    return "|".join(sorted(f"{item.channel_id}:{item.code}" for item in issues))