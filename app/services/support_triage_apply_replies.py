# ruff: noqa: E501
from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.services.support_catalog import (
    support_canned_reply_pack_label,
    support_triage_route_label,
)
from app.services.support_models import (
    SupportTriageApplyActorReply,
    SupportTriageApplyHistory,
    SupportTriageApplyReply,
    SupportTriageApplyRouteActor,
)
from app.services.support_queue_ranking import _support_top_sample_ticket_ids
from app.services.support_triage_apply_notes import (
    _support_triage_apply_actor_reply_note,
    _support_triage_apply_reply_note,
    _support_triage_apply_route_actor_note,
)
from app.utils.datetime import ensure_aware_utc


def _build_support_triage_apply_replies(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyReply]:
    grouped: dict[tuple[str, str | None], dict[str, object]] = {}
    for item in history:
        group_key = (item.reply_key, item.reply_title)
        bucket = grouped.setdefault(
            group_key,
            {
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "apply_count": 0,
                "ticket_count": 0,
                "actor_counts": Counter(),
                "route_pack_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        actor_counts = bucket["actor_counts"]
        if isinstance(actor_counts, Counter):
            actor_counts[item.actor_label or "Unknown"] += 1
        route_pack_counts = bucket["route_pack_counts"]
        if isinstance(route_pack_counts, Counter):
            route_pack_counts[(item.route_key, item.pack_key)] += 1
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

    items: list[SupportTriageApplyReply] = []
    for bucket in grouped.values():
        actor_counts = bucket["actor_counts"]
        top_actor_label = None
        if isinstance(actor_counts, Counter) and actor_counts:
            top_actor_label = sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))[
                0
            ][0]
        route_pack_counts = bucket["route_pack_counts"]
        top_route_key = None
        top_pack_key = None
        route_count = 0
        if isinstance(route_pack_counts, Counter) and route_pack_counts:
            top_route_key, top_pack_key = sorted(
                route_pack_counts.items(),
                key=lambda item: (
                    -item[1],
                    support_triage_route_label(item[0][0]),
                    support_canned_reply_pack_label(item[0][1]),
                ),
            )[0][0]
            route_count = len({route_key for route_key, _pack_key in route_pack_counts})
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
            SupportTriageApplyReply(
                reply_key=str(bucket["reply_key"]),
                reply_title=reply_title,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                actor_count=len(actor_counts) if isinstance(actor_counts, Counter) else 0,
                route_count=route_count,
                top_actor_label=top_actor_label,
                top_route_key=top_route_key,
                top_pack_key=top_pack_key,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_reply_note(
                    reply_title=reply_title,
                    route_key=top_route_key,
                    actor_label=top_actor_label,
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


def _build_support_triage_apply_actor_replies(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyActorReply]:
    grouped: dict[tuple[int | None, str | None, str, str | None], dict[str, object]] = {}
    for item in history:
        group_key = (item.actor_user_id, item.actor_label, item.reply_key, item.reply_title)
        bucket = grouped.setdefault(
            group_key,
            {
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "apply_count": 0,
                "ticket_count": 0,
                "route_pack_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        route_pack_counts = bucket["route_pack_counts"]
        if isinstance(route_pack_counts, Counter):
            route_pack_counts[(item.route_key, item.pack_key)] += 1
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

    items: list[SupportTriageApplyActorReply] = []
    for bucket in grouped.values():
        route_pack_counts = bucket["route_pack_counts"]
        top_route_key = None
        top_pack_key = None
        route_count = 0
        if isinstance(route_pack_counts, Counter) and route_pack_counts:
            top_route_key, top_pack_key = sorted(
                route_pack_counts.items(),
                key=lambda item: (
                    -item[1],
                    support_triage_route_label(item[0][0]),
                    support_canned_reply_pack_label(item[0][1]),
                ),
            )[0][0]
            route_count = len({route_key for route_key, _pack_key in route_pack_counts})
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        sample_ticket_ids = (
            _support_top_sample_ticket_ids(ranked_ticket_ids, limit=3)
            if isinstance(ranked_ticket_ids, list)
            else ()
        )
        apply_count = int(bucket["apply_count"])
        ticket_count = int(bucket["ticket_count"])
        latest_applied_at = ensure_aware_utc(bucket["latest_applied_at"])
        actor_label = (
            str(bucket["actor_label"]).strip() if bucket.get("actor_label") is not None else None
        )
        reply_title = (
            str(bucket["reply_title"]).strip() if bucket.get("reply_title") is not None else None
        )
        items.append(
            SupportTriageApplyActorReply(
                actor_user_id=(
                    int(bucket["actor_user_id"])
                    if bucket.get("actor_user_id") is not None
                    else None
                ),
                actor_label=actor_label,
                reply_key=str(bucket["reply_key"]),
                reply_title=reply_title,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                route_count=route_count,
                top_route_key=top_route_key,
                top_pack_key=top_pack_key,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_actor_reply_note(
                    actor_label=actor_label,
                    reply_title=reply_title,
                    route_key=top_route_key,
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
            item.reply_title or item.reply_key,
        ),
    )


def _build_support_triage_apply_route_actors(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyRouteActor]:
    grouped: dict[tuple[str, int | None, str | None], dict[str, object]] = {}
    for item in history:
        group_key = (item.route_key, item.actor_user_id, item.actor_label)
        bucket = grouped.setdefault(
            group_key,
            {
                "route_key": item.route_key,
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "apply_count": 0,
                "ticket_count": 0,
                "reply_pack_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        reply_pack_counts = bucket["reply_pack_counts"]
        if isinstance(reply_pack_counts, Counter):
            reply_pack_counts[(item.reply_key, item.reply_title, item.pack_key)] += 1
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

    items: list[SupportTriageApplyRouteActor] = []
    for bucket in grouped.values():
        reply_pack_counts = bucket["reply_pack_counts"]
        top_reply_key = None
        top_reply_title = None
        top_pack_key = None
        reply_count = 0
        if isinstance(reply_pack_counts, Counter) and reply_pack_counts:
            top_reply_key, top_reply_title, top_pack_key = sorted(
                reply_pack_counts.items(),
                key=lambda item: (
                    -item[1],
                    str(item[0][1] or item[0][0]),
                    support_canned_reply_pack_label(item[0][2]),
                ),
            )[0][0]
            reply_count = len(
                {reply_key for reply_key, _reply_title, _pack_key in reply_pack_counts}
            )
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        sample_ticket_ids = (
            _support_top_sample_ticket_ids(ranked_ticket_ids, limit=3)
            if isinstance(ranked_ticket_ids, list)
            else ()
        )
        route_key = str(bucket["route_key"])
        actor_label = (
            str(bucket["actor_label"]).strip() if bucket.get("actor_label") is not None else None
        )
        apply_count = int(bucket["apply_count"])
        ticket_count = int(bucket["ticket_count"])
        latest_applied_at = ensure_aware_utc(bucket["latest_applied_at"])
        items.append(
            SupportTriageApplyRouteActor(
                route_key=route_key,
                actor_user_id=(
                    int(bucket["actor_user_id"])
                    if bucket.get("actor_user_id") is not None
                    else None
                ),
                actor_label=actor_label,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                reply_count=reply_count,
                top_reply_key=top_reply_key,
                top_reply_title=top_reply_title,
                top_pack_key=top_pack_key,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_route_actor_note(
                    route_key=route_key,
                    actor_label=actor_label,
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
            support_triage_route_label(item.route_key),
            item.actor_label or "",
        ),
    )
