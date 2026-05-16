from __future__ import annotations

from app.services.support_catalog import (
    support_canned_reply_pack_label,
    support_triage_route_label,
)


def _support_triage_apply_route_note(
    *,
    route_key: str,
    reply_title: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    route_label = support_triage_route_label(route_key)
    reply_label = reply_title or "canned reply"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f'{route_label} -> "{reply_label}" across '
        f"{apply_count} {apply_label} / {ticket_count} {ticket_label}."
    )


def _support_triage_apply_actor_note(
    *,
    actor_label: str | None,
    route_key: str | None,
    reply_title: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    actor_name = actor_label or "Unknown actor"
    route_label = support_triage_route_label(route_key) if route_key else "mixed routes"
    reply_label = reply_title or "canned reply"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f"{actor_name} handled {apply_count} {apply_label} / {ticket_count} "
        f'{ticket_label}. Most often {route_label} -> "{reply_label}".'
    )


def _support_triage_apply_reply_note(
    *,
    reply_title: str | None,
    route_key: str | None,
    actor_label: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    reply_label = reply_title or "canned reply"
    route_label = support_triage_route_label(route_key) if route_key else "mixed routes"
    actor_name = actor_label or "mixed actors"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f'"{reply_label}" ran across {apply_count} {apply_label} / {ticket_count} '
        f"{ticket_label}. Mostly {actor_name} on {route_label}."
    )


def _support_triage_apply_actor_reply_note(
    *,
    actor_label: str | None,
    reply_title: str | None,
    route_key: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    actor_name = actor_label or "Unknown actor"
    reply_label = reply_title or "canned reply"
    route_label = support_triage_route_label(route_key) if route_key else "mixed routes"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f'{actor_name} used "{reply_label}" across {apply_count} {apply_label} / '
        f"{ticket_count} {ticket_label}. Mostly on {route_label}."
    )


def _support_triage_apply_route_actor_note(
    *,
    route_key: str,
    actor_label: str | None,
    reply_title: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    route_label = support_triage_route_label(route_key)
    actor_name = actor_label or "Unknown actor"
    reply_label = reply_title or "canned reply"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f"{route_label} with {actor_name} across {apply_count} {apply_label} / "
        f'{ticket_count} {ticket_label}. Most often "{reply_label}".'
    )


def _support_triage_apply_reply_pack_note(
    *,
    reply_title: str | None,
    pack_key: str,
    route_key: str | None,
    actor_label: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    reply_label = reply_title or "canned reply"
    pack_label = support_canned_reply_pack_label(pack_key)
    route_label = support_triage_route_label(route_key) if route_key else "mixed routes"
    actor_name = actor_label or "mixed actors"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f'"{reply_label}" in {pack_label} across {apply_count} {apply_label} / '
        f"{ticket_count} {ticket_label}. Mostly {actor_name} on {route_label}."
    )


def _support_triage_apply_route_reply_actor_note(
    *,
    route_key: str,
    reply_title: str | None,
    actor_label: str | None,
    pack_key: str | None,
    apply_count: int,
    ticket_count: int,
) -> str:
    route_label = support_triage_route_label(route_key)
    reply_label = reply_title or "canned reply"
    actor_name = actor_label or "Unknown actor"
    pack_label = support_canned_reply_pack_label(pack_key) if pack_key else "mixed packs"
    apply_label = "apply" if apply_count == 1 else "applies"
    ticket_label = "ticket" if ticket_count == 1 else "tickets"
    return (
        f'{route_label} -> "{reply_label}" by {actor_name} across {apply_count} '
        f"{apply_label} / {ticket_count} {ticket_label} in {pack_label}."
    )
