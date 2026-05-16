# ruff: noqa: E501
from __future__ import annotations

from app.services.support_catalog import (
    support_canned_reply_pack_label,
    support_triage_route_label,
)
from app.services.support_models import (
    SupportInsights,
    SupportTriageApplyEffectiveness,
    SupportTriageApplyFocus,
)


def _support_triage_apply_focus_source_priority(source_key: str) -> int:
    priorities = {
        "route_reply_actor": 0,
        "route_actor": 1,
        "actor_reply": 2,
        "reply_pack": 3,
    }
    return priorities.get(source_key, 99)


def _build_support_triage_apply_focus(
    insights: SupportInsights,
) -> list[SupportTriageApplyFocus]:
    items: list[SupportTriageApplyFocus] = []

    for item in insights.triage_apply_route_reply_actors:
        title = (
            f"{support_triage_route_label(item.route_key)} -> "
            f"{item.reply_title or item.reply_key} -> {item.actor_label or 'Unknown'}"
        )
        secondary_label = (
            support_canned_reply_pack_label(item.top_pack_key) if item.top_pack_key else None
        )
        items.append(
            SupportTriageApplyFocus(
                key=(
                    f"route_reply_actor:{item.route_key}:{item.reply_key}:"
                    f"{item.actor_user_id or item.actor_label or 'unknown'}"
                ),
                source_key="route_reply_actor",
                source_label="Route x reply x actor",
                title=title,
                secondary_label=secondary_label,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                focus_score=item.ticket_count * 100 + item.apply_count * 10,
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    for item in insights.triage_apply_route_actors:
        secondary_parts = [
            item.top_reply_title or item.top_reply_key,
            support_canned_reply_pack_label(item.top_pack_key) if item.top_pack_key else None,
        ]
        secondary_label = " / ".join(part for part in secondary_parts if part)
        items.append(
            SupportTriageApplyFocus(
                key=f"route_actor:{item.route_key}:{item.actor_user_id or item.actor_label or 'unknown'}",
                source_key="route_actor",
                source_label="Route x actor",
                title=(
                    f"{support_triage_route_label(item.route_key)} -> "
                    f"{item.actor_label or 'Unknown'}"
                ),
                secondary_label=secondary_label or None,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                focus_score=item.ticket_count * 100 + item.apply_count * 10,
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    for item in insights.triage_apply_actor_replies:
        secondary_parts = [
            support_triage_route_label(item.top_route_key) if item.top_route_key else None,
            support_canned_reply_pack_label(item.top_pack_key) if item.top_pack_key else None,
        ]
        secondary_label = " / ".join(part for part in secondary_parts if part)
        items.append(
            SupportTriageApplyFocus(
                key=f"actor_reply:{item.actor_user_id or item.actor_label or 'unknown'}:{item.reply_key}",
                source_key="actor_reply",
                source_label="Actor x reply",
                title=f"{item.actor_label or 'Unknown'} -> {item.reply_title or item.reply_key}",
                secondary_label=secondary_label or None,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                focus_score=item.ticket_count * 100 + item.apply_count * 10,
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    for item in insights.triage_apply_reply_packs:
        secondary_parts = [
            support_triage_route_label(item.top_route_key) if item.top_route_key else None,
            item.top_actor_label,
        ]
        secondary_label = " / ".join(part for part in secondary_parts if part)
        items.append(
            SupportTriageApplyFocus(
                key=f"reply_pack:{item.reply_key}:{item.pack_key}",
                source_key="reply_pack",
                source_label="Reply x pack",
                title=(
                    f"{item.reply_title or item.reply_key} -> "
                    f"{support_canned_reply_pack_label(item.pack_key)}"
                ),
                secondary_label=secondary_label or None,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                focus_score=item.ticket_count * 100 + item.apply_count * 10,
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            -item.focus_score,
            -int(item.latest_applied_at.timestamp()),
            _support_triage_apply_focus_source_priority(item.source_key),
            item.title,
        ),
    )


def _build_support_triage_apply_effectiveness(
    insights: SupportInsights,
) -> list[SupportTriageApplyEffectiveness]:
    items: list[SupportTriageApplyEffectiveness] = []

    for item in insights.triage_apply_route_reply_actors:
        items.append(
            SupportTriageApplyEffectiveness(
                key=(
                    f"route_reply_actor:{item.route_key}:{item.reply_key}:"
                    f"{item.actor_user_id or item.actor_label or 'unknown'}"
                ),
                source_key="route_reply_actor",
                source_label="Route x reply x actor",
                title=(
                    f"{support_triage_route_label(item.route_key)} -> "
                    f"{item.reply_title or item.reply_key} -> {item.actor_label or 'Unknown'}"
                ),
                secondary_label=(
                    support_canned_reply_pack_label(item.top_pack_key)
                    if item.top_pack_key
                    else None
                ),
                route_key=item.route_key,
                reply_key=item.reply_key,
                reply_title=item.reply_title,
                actor_user_id=item.actor_user_id,
                actor_label=item.actor_label,
                pack_key=item.top_pack_key,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                coverage_count=1,
                effectiveness_score=(
                    item.ticket_count * 100 + item.apply_count * 10 + 1 * 5 + 40
                ),
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    for item in insights.triage_apply_route_actors:
        secondary_parts = [
            item.top_reply_title or item.top_reply_key,
            support_canned_reply_pack_label(item.top_pack_key) if item.top_pack_key else None,
        ]
        items.append(
            SupportTriageApplyEffectiveness(
                key=(
                    f"route_actor:{item.route_key}:"
                    f"{item.actor_user_id or item.actor_label or 'unknown'}"
                ),
                source_key="route_actor",
                source_label="Route x actor",
                title=(
                    f"{support_triage_route_label(item.route_key)} -> "
                    f"{item.actor_label or 'Unknown'}"
                ),
                secondary_label=" / ".join(part for part in secondary_parts if part) or None,
                route_key=item.route_key,
                reply_key=item.top_reply_key,
                reply_title=item.top_reply_title,
                actor_user_id=item.actor_user_id,
                actor_label=item.actor_label,
                pack_key=item.top_pack_key,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                coverage_count=item.reply_count,
                effectiveness_score=(
                    item.ticket_count * 100
                    + item.apply_count * 10
                    + item.reply_count * 5
                    + 30
                ),
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    for item in insights.triage_apply_actor_replies:
        secondary_parts = [
            support_triage_route_label(item.top_route_key) if item.top_route_key else None,
            support_canned_reply_pack_label(item.top_pack_key) if item.top_pack_key else None,
        ]
        items.append(
            SupportTriageApplyEffectiveness(
                key=(
                    f"actor_reply:{item.actor_user_id or item.actor_label or 'unknown'}:"
                    f"{item.reply_key}"
                ),
                source_key="actor_reply",
                source_label="Actor x reply",
                title=f"{item.actor_label or 'Unknown'} -> {item.reply_title or item.reply_key}",
                secondary_label=" / ".join(part for part in secondary_parts if part) or None,
                route_key=item.top_route_key,
                reply_key=item.reply_key,
                reply_title=item.reply_title,
                actor_user_id=item.actor_user_id,
                actor_label=item.actor_label,
                pack_key=item.top_pack_key,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                coverage_count=item.route_count,
                effectiveness_score=(
                    item.ticket_count * 100
                    + item.apply_count * 10
                    + item.route_count * 5
                    + 20
                ),
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    for item in insights.triage_apply_reply_packs:
        secondary_parts = [
            support_triage_route_label(item.top_route_key) if item.top_route_key else None,
            item.top_actor_label,
        ]
        items.append(
            SupportTriageApplyEffectiveness(
                key=f"reply_pack:{item.reply_key}:{item.pack_key}",
                source_key="reply_pack",
                source_label="Reply x pack",
                title=(
                    f"{item.reply_title or item.reply_key} -> "
                    f"{support_canned_reply_pack_label(item.pack_key)}"
                ),
                secondary_label=" / ".join(part for part in secondary_parts if part) or None,
                route_key=item.top_route_key,
                reply_key=item.reply_key,
                reply_title=item.reply_title,
                actor_user_id=None,
                actor_label=item.top_actor_label,
                pack_key=item.pack_key,
                sample_ticket_ids=item.sample_ticket_ids,
                apply_count=item.apply_count,
                ticket_count=item.ticket_count,
                coverage_count=item.actor_count,
                effectiveness_score=(
                    item.ticket_count * 100
                    + item.apply_count * 10
                    + item.actor_count * 5
                    + 10
                ),
                latest_applied_at=item.latest_applied_at,
                note=item.note,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            -item.effectiveness_score,
            -int(item.latest_applied_at.timestamp()),
            _support_triage_apply_focus_source_priority(item.source_key),
            item.title,
        ),
    )
