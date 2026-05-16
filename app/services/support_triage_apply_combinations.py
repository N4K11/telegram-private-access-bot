# ruff: noqa: E501
from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.services.support_catalog import (
    support_canned_reply_pack_label,
    support_triage_route_label,
)
from app.services.support_models import (
    SupportTriageApplyHistory,
    SupportTriageApplyReplyPack,
    SupportTriageApplyRouteReplyActor,
)
from app.services.support_queue_ranking import _support_top_sample_ticket_ids
from app.services.support_triage_apply_notes import (
    _support_triage_apply_reply_pack_note,
    _support_triage_apply_route_reply_actor_note,
)
from app.utils.datetime import ensure_aware_utc


def _build_support_triage_apply_reply_packs(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyReplyPack]:
    grouped: dict[tuple[str, str | None, str], dict[str, object]] = {}
    for item in history:
        group_key = (item.reply_key, item.reply_title, item.pack_key)
        bucket = grouped.setdefault(
            group_key,
            {
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "pack_key": item.pack_key,
                "apply_count": 0,
                "ticket_count": 0,
                "actor_counts": Counter(),
                "route_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        actor_counts = bucket["actor_counts"]
        if isinstance(actor_counts, Counter):
            actor_counts[item.actor_label or "Unknown"] += 1
        route_counts = bucket["route_counts"]
        if isinstance(route_counts, Counter):
            route_counts[item.route_key] += 1
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

    items: list[SupportTriageApplyReplyPack] = []
    for bucket in grouped.values():
        actor_counts = bucket["actor_counts"]
        top_actor_label = None
        if isinstance(actor_counts, Counter) and actor_counts:
            top_actor_label = sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))[
                0
            ][0]
        route_counts = bucket["route_counts"]
        top_route_key = None
        if isinstance(route_counts, Counter) and route_counts:
            top_route_key = sorted(
                route_counts.items(),
                key=lambda item: (-item[1], support_triage_route_label(item[0])),
            )[0][0]
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
        pack_key = str(bucket["pack_key"])
        items.append(
            SupportTriageApplyReplyPack(
                reply_key=str(bucket["reply_key"]),
                reply_title=reply_title,
                pack_key=pack_key,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                actor_count=len(actor_counts) if isinstance(actor_counts, Counter) else 0,
                top_actor_label=top_actor_label,
                top_route_key=top_route_key,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_reply_pack_note(
                    reply_title=reply_title,
                    pack_key=pack_key,
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
            support_canned_reply_pack_label(item.pack_key),
        ),
    )


def _build_support_triage_apply_route_reply_actors(
    history: list[SupportTriageApplyHistory],
) -> list[SupportTriageApplyRouteReplyActor]:
    grouped: dict[tuple[str, str, str | None, int | None, str | None], dict[str, object]] = {}
    for item in history:
        group_key = (
            item.route_key,
            item.reply_key,
            item.reply_title,
            item.actor_user_id,
            item.actor_label,
        )
        bucket = grouped.setdefault(
            group_key,
            {
                "route_key": item.route_key,
                "reply_key": item.reply_key,
                "reply_title": item.reply_title,
                "actor_user_id": item.actor_user_id,
                "actor_label": item.actor_label,
                "apply_count": 0,
                "ticket_count": 0,
                "pack_counts": Counter(),
                "latest_applied_at": item.created_at,
                "ranked_ticket_ids": [],
            },
        )
        bucket["apply_count"] = int(bucket["apply_count"]) + 1
        bucket["ticket_count"] = int(bucket["ticket_count"]) + item.count
        pack_counts = bucket["pack_counts"]
        if isinstance(pack_counts, Counter):
            pack_counts[item.pack_key] += 1
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

    items: list[SupportTriageApplyRouteReplyActor] = []
    for bucket in grouped.values():
        pack_counts = bucket["pack_counts"]
        top_pack_key = None
        if isinstance(pack_counts, Counter) and pack_counts:
            top_pack_key = sorted(
                pack_counts.items(),
                key=lambda item: (-item[1], support_canned_reply_pack_label(item[0])),
            )[0][0]
        ranked_ticket_ids = bucket["ranked_ticket_ids"]
        sample_ticket_ids = (
            _support_top_sample_ticket_ids(ranked_ticket_ids, limit=3)
            if isinstance(ranked_ticket_ids, list)
            else ()
        )
        route_key = str(bucket["route_key"])
        reply_key = str(bucket["reply_key"])
        reply_title = (
            str(bucket["reply_title"]).strip() if bucket.get("reply_title") is not None else None
        )
        actor_label = (
            str(bucket["actor_label"]).strip() if bucket.get("actor_label") is not None else None
        )
        apply_count = int(bucket["apply_count"])
        ticket_count = int(bucket["ticket_count"])
        latest_applied_at = ensure_aware_utc(bucket["latest_applied_at"])
        items.append(
            SupportTriageApplyRouteReplyActor(
                route_key=route_key,
                reply_key=reply_key,
                reply_title=reply_title,
                actor_user_id=(
                    int(bucket["actor_user_id"])
                    if bucket.get("actor_user_id") is not None
                    else None
                ),
                actor_label=actor_label,
                sample_ticket_ids=sample_ticket_ids,
                apply_count=apply_count,
                ticket_count=ticket_count,
                top_pack_key=top_pack_key,
                latest_applied_at=latest_applied_at,
                note=_support_triage_apply_route_reply_actor_note(
                    route_key=route_key,
                    reply_title=reply_title,
                    actor_label=actor_label,
                    pack_key=top_pack_key,
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
            item.reply_title or item.reply_key,
            item.actor_label or "",
        ),
    )
