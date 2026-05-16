# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timedelta

from app.config import Settings
from app.db.models import Payment, SupportTicket
from app.services.support import (
    SUPPORT_CATEGORY_ACCESS,
    SUPPORT_CATEGORY_PAYMENT,
    SUPPORT_CATEGORY_TECHNICAL,
    SUPPORT_PRIORITY_HIGH,
    SUPPORT_PRIORITY_URGENT,
    SUPPORT_SLA_BUCKET_BREACH,
    SUPPORT_SLA_BUCKET_LABELS,
    SUPPORT_SLA_BUCKET_WARNING,
    build_support_canned_replies,
    support_action_lane,
    support_action_lane_label,
    support_canned_reply_pack_key,
    support_canned_reply_pack_label,
    support_canned_reply_pack_titles,
    support_escalation_action_label,
    support_escalation_lane,
    support_escalation_lane_label,
    support_next_action_label,
    support_next_action_note,
    support_next_action_severity,
    support_priority_label,
    support_sla_bucket,
    support_sla_due_hours,
)
from app.services.support_catalog import SUPPORT_WAITING_STATE_LABELS
from app.services.web_admin_dashboard_common import _channel_name as _channel_name
from app.services.web_admin_dashboard_common import _display_name as _display_name
from app.services.web_admin_dashboard_common import _dt as _dt
from app.services.web_admin_dashboard_common import _payment_amount as _payment_amount
from app.services.web_admin_dashboard_common import _plain as _plain
from app.services.web_admin_dashboard_common import _tariff_name as _tariff_name
from app.services.web_admin_dashboard_support_ticket_list_serializers import (
    _is_support_ticket_stale,
    _support_waiting_state,
)
from app.utils.datetime import ensure_aware_utc


def _serialize_support_canned_replies(ticket: SupportTicket) -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "title": item.title,
            "body": item.body,
            "kind": item.kind,
        }
        for item in build_support_canned_replies(ticket)
    ]


def _hours_since(reference_time: datetime, value: datetime | None) -> float | None:
    if value is None:
        return None
    delta = ensure_aware_utc(reference_time) - ensure_aware_utc(value)
    return round(max(delta.total_seconds() / 3600, 0), 1)


def _serialize_support_ticket_pinned_context(
    ticket: SupportTicket,
    *,
    profile_snapshot,
    payments: list[Payment],
    settings: Settings,
    reference_time: datetime,
    triage_batch: dict[str, object] | None = None,
) -> dict[str, object]:
    waiting_state = _support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=reference_time)
    next_action = _serialize_support_next_action(ticket, reference_time=reference_time)
    triage_pack_key = support_canned_reply_pack_key(ticket)
    triage_route_label = support_escalation_action_label(
        next_action["escalation_key"],
        next_action["key"],
    )
    latest_payment = payments[0] if payments else None
    return {
        "queue_label": SUPPORT_WAITING_STATE_LABELS.get(waiting_state, waiting_state),
        "sla_bucket_label": SUPPORT_SLA_BUCKET_LABELS.get(sla_bucket, sla_bucket),
        "priority_label": support_priority_label(ticket.priority),
        "action_lane_label": support_action_lane_label(
            support_action_lane(ticket, now=reference_time)
        ),
        "escalation_lane_label": support_escalation_lane_label(
            support_escalation_lane(ticket, now=reference_time)
        ),
        "next_action_label": next_action["label"],
        "next_action_note": next_action["note"],
        "next_action_severity": next_action["severity"],
        "triage_pack_key": triage_pack_key,
        "triage_pack_label": support_canned_reply_pack_label(triage_pack_key),
        "triage_sample_titles": support_canned_reply_pack_titles(triage_pack_key),
        "triage_route_label": triage_route_label,
        "triage_batch_count": (
            triage_batch["count"] if triage_batch is not None else 0
        ),
        "triage_batch_sample_ticket_ids": (
            triage_batch["sample_ticket_ids"] if triage_batch is not None else []
        ),
        "triage_primary_reply_title": (
            triage_batch["primary_reply_title"] if triage_batch is not None else None
        ),
        "triage_primary_reply_kind": (
            triage_batch["primary_reply_kind"] if triage_batch is not None else None
        ),
        "triage_batch_note": triage_batch["note"] if triage_batch is not None else None,
        "open_age_hours": _hours_since(reference_time, ticket.created_at),
        "idle_hours": _hours_since(reference_time, ticket.updated_at),
        "last_user_message_at_label": _dt(ticket.last_user_message_at, settings.timezone),
        "last_user_gap_hours": _hours_since(reference_time, ticket.last_user_message_at),
        "last_admin_message_at_label": _dt(ticket.last_admin_message_at, settings.timezone),
        "last_admin_gap_hours": _hours_since(reference_time, ticket.last_admin_message_at),
        "active_subscription_count": (
            profile_snapshot.active_subscription_count if profile_snapshot is not None else 0
        ),
        "current_tariff_label": (
            profile_snapshot.current_tariff_label if profile_snapshot is not None else None
        ),
        "current_channel_label": (
            profile_snapshot.current_channel_label if profile_snapshot is not None else None
        ),
        "remaining_label": (
            profile_snapshot.remaining_label if profile_snapshot is not None else None
        ),
        "latest_payment_amount_label": (
            _payment_amount(latest_payment) if latest_payment is not None else None
        ),
        "latest_payment_provider_label": (
            "Crypto Pay"
            if latest_payment is not None and latest_payment.provider.startswith("crypto")
            else ("Telegram Stars" if latest_payment is not None else None)
        ),
        "latest_payment_paid_at_label": (
            _dt(latest_payment.paid_at, settings.timezone) if latest_payment is not None else None
        ),
        "latest_payment_age_hours": (
            _hours_since(reference_time, latest_payment.paid_at)
            if latest_payment is not None
            else None
        ),
    }


def _serialize_support_next_action(
    ticket: SupportTicket,
    *,
    reference_time: datetime,
) -> dict[str, object]:
    action_lane = support_action_lane(ticket, now=reference_time)
    escalation_lane = support_escalation_lane(ticket, now=reference_time)
    return {
        "key": action_lane,
        "label": support_next_action_label(ticket, now=reference_time),
        "note": support_next_action_note(ticket, now=reference_time),
        "severity": support_next_action_severity(ticket, now=reference_time),
        "escalation_key": escalation_lane,
        "escalation_label": support_escalation_lane_label(escalation_lane),
    }


def _build_support_operator_hints(
    ticket: SupportTicket,
    *,
    profile_snapshot,
    payments: list[Payment],
    reference_time: datetime,
) -> list[dict[str, object]]:
    hints: list[dict[str, object]] = []
    seen: set[str] = set()
    stale_before = reference_time - timedelta(hours=24)
    waiting_state = _support_waiting_state(ticket)
    sla_bucket = support_sla_bucket(ticket, now=reference_time)
    idle_hours = _hours_since(reference_time, ticket.updated_at)
    due_hours = support_sla_due_hours(ticket)

    def add_hint(key: str, label: str, note: str, *, severity: str) -> None:
        if key in seen:
            return
        seen.add(key)
        hints.append(
            {
                "key": key,
                "label": label,
                "note": note,
                "severity": severity,
            }
        )

    if ticket.status != "open":
        add_hint(
            "closed_ticket",
            "????? ??? ??????",
            "???? ???????????? ???????? ? ????? ?????????, ????? ??????? ????? ?????? ? ??????????? ????????.",
            severity="info",
        )
        return hints

    if sla_bucket == SUPPORT_SLA_BUCKET_BREACH:
        add_hint(
            "reply_now",
            "????? ????? ????? ??????",
            f"SLA ??? ???????: ??? ??????? {idle_hours}? ??? ?????? {due_hours}?.",
            severity="warn",
        )
    elif sla_bucket == SUPPORT_SLA_BUCKET_WARNING:
        add_hint(
            "sla_warning",
            "????? ???????? ? ??????? SLA",
            f"?? breach ???????? ???? ???????: ??????? idle {idle_hours}? ?? {due_hours}?.",
            severity="info",
        )

    if _is_support_ticket_stale(ticket, stale_before=stale_before):
        add_hint(
            "stale_thread",
            "????? ?????????",
            "????? ??? ??????? ??????? ?????? 24 ?????: ???? ????????, ???? ????????? ?? ? ????? ???????? ????????????.",
            severity="warn",
        )

    if ticket.priority in {SUPPORT_PRIORITY_HIGH, SUPPORT_PRIORITY_URGENT}:
        add_hint(
            "high_priority_watch",
            "??????? ?????????",
            "???? ????? ?????? ?????????? ? ???????? ??????? ?? ?????? ????????????? ??????? ?? ??????? ????????????.",
            severity="warn",
        )

    if waiting_state == "awaiting_admin":
        if ticket.category == SUPPORT_CATEGORY_PAYMENT:
            add_hint(
                "payment_review",
                "????????? ?????? ? ?????????",
                "??????? ??????, ?????, ?????? ???????? ? ???? ?????? ??????? ????? ????????? ???????.",
                severity="warn" if payments else "info",
            )
        elif ticket.category == SUPPORT_CATEGORY_ACCESS:
            add_hint(
                "access_review",
                "????????? ?????? ? ??????",
                "????????? ???????? ????????, ??????-?????? ? ?????? ????? ???????????? ? ?????.",
                severity="warn",
            )
        elif ticket.category == SUPPORT_CATEGORY_TECHNICAL:
            add_hint(
                "technical_triage",
                "????? ??????????? triage-????????",
                "???????? ???? ???????????????, ?????? ????? ? ???????????, ??? ?????? ??? ?????????.",
                severity="info",
            )
        else:
            add_hint(
                "clarify_request",
                "????? ?????????????? ?????",
                "?????? ????????? ??? ? ???? ???? ???????, ???? ???? ????????? ??????????? ??????.",
                severity="info",
            )
    elif waiting_state == "awaiting_user":
        add_hint(
            "waiting_user_followup",
            "?????? ??????? ?? ????????????",
            "????? ???????????? follow-up canned reply ??? ????????? ??????? ????? ??? ?????? ?????????? ??????.",
            severity="info",
        )

    if payments and profile_snapshot is not None and not profile_snapshot.current_channel_label:
        add_hint(
            "access_gap_after_payment",
            "????? ?????? ??? ????????? ???????",
            "???? ?????????? ???????, ?? ???????? ????? ?? ?????: ????????? ????????? ???????? ? ?????????? ??????.",
            severity="warn",
        )

    if (
        ticket.category == SUPPORT_CATEGORY_ACCESS
        and profile_snapshot is not None
        and profile_snapshot.current_channel_label
        and waiting_state == "awaiting_admin"
    ):
        add_hint(
            "verify_join_state",
            "?????? ???????, ?? ????? live-check ?????",
            "???????? ???????: ?????????, ?? ?????? ?? ???????????? ? expired invite ??? ??????????? Telegram ?? ????.",
            severity="info",
        )

    return hints


def _serialize_support_profile_summary(snapshot, *, settings: Settings) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "telegram_id": snapshot.user.telegram_id,
        "display_name": _display_name(snapshot.user),
        "status_label": snapshot.status_label,
        "latest_expires_at_label": _dt(snapshot.latest_expires_at, settings.timezone),
        "remaining_label": snapshot.remaining_label,
        "current_tariff_label": snapshot.current_tariff_label,
        "current_channel_label": snapshot.current_channel_label,
        "active_subscription_count": snapshot.active_subscription_count,
        "total_stars_amount": snapshot.total_stars_amount,
    }
