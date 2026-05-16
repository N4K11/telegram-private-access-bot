# ruff: noqa: E501
from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.services.support_catalog import support_triage_route_label
from app.services.support_models import (
    SupportTriageApplyActor,
    SupportTriageApplyHistory,
    SupportTriageApplyRoute,
)
from app.services.support_queue_ranking import _support_top_sample_ticket_ids
from app.services.support_triage_apply_notes import (
    _support_triage_apply_actor_note,
    _support_triage_apply_route_note,
)
from app.utils.datetime import ensure_aware_utc


def _build_support_triage_apply_routes(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyRoute]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for item in history:
        group_key = (item.route_key, item.pack_key, item.reply_key)
        bucket = grouped.setdefault(
            group_key,
            {
                "route_key": item.route_key,
                "pack_key": item.pack_key,
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "apply_count": 0,
                "ticket_count": 0,
                "actor_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        actor_label = item.actor_label or "Unknown"
        actor_counts = bucket["actor_counts"]
        if isinstance(actor_counts, Counter):
            actor_counts[actor_label] += 1
        latest_applied_at = bucket["latest_applied_at"]
        if isinstance(latest_applied_at, datetime) and item.created_at > latest_applied_at:
            bucket["latest_applied_at"] = item.created_at
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        if isinstance(ranked_ticket_ids, list):
            for position, ticket_id in enumerate(item.ticket_ids):
                ranked_ticket_ids.append(
                    (
                        (
                            -int(item.created_at.timestamp()),
                            position,
                            ticket_id,
                        ),
                        ticket_id,
                    )
                )

    items: list[SupportTriageApplyRoute] = []
    for group_key, bucket in grouped.items():
        route_key, pack_key, reply_key = group_key
        actor_counts = bucket["actor_counts"]
        top_actor_label = None
        if isinstance(actor_counts, Counter) and actor_counts:
            top_actor_label = sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))[
                0
            ][0]
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        sample_ticket_ids = (
            _support_top_sample_ticket_ids(ranked_ticket_ids, limit=3)
            if isinstance(ranked_ticket_ids, list)
            else ()
        )
        apply_count = int(bucket["apply_count"])
        ticket_count = int(bucket["ticket_count"])
        latest_applied_at = ensure_aware_utc(bucket["latest_applied_at"])
        reply_title = (
            str(bucket["reply_title"]).strip() if bucket.get("reply_title") is not None else None
        )
        items.append(
            SupportTriageApplyRoute(
                key=f"{route_key}:{pack_key}:{reply_key}",
                route_key=route_key,
                pack_key=pack_key,
                reply_key=reply_key,
                reply_title=reply_title,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                actor_count=len(actor_counts) if isinstance(actor_counts, Counter) else 0,
                top_actor_label=top_actor_label,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_route_note(
                    route_key=route_key,
                    reply_title=reply_title,
                    apply_count=apply_count,
                    ticket_count=ticket_count,
                ),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.ticket_count,
            -item.apply_count,
            -int(item.latest_applied_at.timestamp()),
            item.reply_title or item.reply_key,
        ),
    )


def _build_support_triage_apply_actors(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyActor]:
    grouped: dict[tuple[int | None, str | None], dict[str, object]] = {}
    for item in history:
        group_key = (item.actor_user_id, item.actor_label)
        bucket = grouped.setdefault(
            group_key,
            {
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "apply_count": 0,
                "ticket_count": 0,
                "route_keys": set(),
                "route_reply_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        route_keys = bucket["route_keys"]
        if isinstance(route_keys, set):
            route_keys.add(item.route_key)
        route_reply_counts = bucket["route_reply_counts"]
        if isinstance(route_reply_counts, Counter):
            route_reply_counts[(item.route_key, item.reply_key, item.reply_title)] += 1
        latest_applied_at = bucket["latest_applied_at"]
        if isinstance(latest_applied_at, datetime) and item.created_at > latest_applied_at:
            bucket["latest_applied_at"] = item.created_at
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        if isinstance(ranked_ticket_ids, list):
            for position, ticket_id in enumerate(item.ticket_ids):
                ranked_ticket_ids.append(
                    (
                        (
                            -int(item.created_at.timestamp()),
                            position,
                            ticket_id,
                        ),
                        ticket_id,
                    )
                )

    items: list[SupportTriageApplyActor] = []
    for bucket in grouped.values():
        route_reply_counts = bucket["route_reply_counts"]
        top_route_key = None
        top_reply_key = None
        top_reply_title = None
        if isinstance(route_reply_counts, Counter) and route_reply_counts:
            top_route_key, top_reply_key, top_reply_title = sorted(
                route_reply_counts.items(),
                key=lambda item: (
                    -item[1],
                    support_triage_route_label(item[0][0]),
                    str(item[0][2] or item[0][1]),
                ),
            )[0][0]
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        sample_ticket_ids = (
            _support_top_sample_ticket_ids(ranked_ticket_ids, limit=3)
            if isinstance(ranked_ticket_ids, list)
            else ()
        )
        route_keys = bucket["route_keys"]
        route_count = len(route_keys) if isinstance(route_keys, set) else 0
        apply_count = int(bucket["apply_count"])
        ticket_count = int(bucket["ticket_count"])
        latest_applied_at = ensure_aware_utc(bucket["latest_applied_at"])
        actor_label = (
            str(bucket["actor_label"]).strip() if bucket.get("actor_label") is not None else None
        )
        items.append(
            SupportTriageApplyActor(
                actor_user_id=(
                    int(bucket["actor_user_id"])
                    if bucket.get("actor_user_id") is not None
                    else None
                ),
                actor_label=actor_label,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                route_count=route_count,
                top_route_key=top_route_key,
                top_reply_key=top_reply_key,
                top_reply_title=top_reply_title,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_actor_note(
                    actor_label=actor_label,
                    route_key=top_route_key,
                    reply_title=top_reply_title,
                    apply_count=apply_count,
                    ticket_count=ticket_count,
                ),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            -item.ticket_count,
            -item.apply_count,
            -int(item.latest_applied_at.timestamp()),
            item.actor_label or "",
        ),
    )
