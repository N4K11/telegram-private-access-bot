# ruff: noqa: E501
from __future__ import annotations

_EMPTY_LIST_DEFAULT = object()


def _first_support_triage_item(
    items: list[dict[str, object]],
) -> dict[str, object] | None:
    return items[0] if items else None


def _support_triage_summary_value(
    item: dict[str, object] | None,
    key: str,
    default: object = None,
) -> object:
    if item is None:
        return default
    return item[key]


def _support_triage_field_default(field: tuple[object, ...]) -> object:
    if len(field) < 3:
        return None
    default = field[2]
    if default is _EMPTY_LIST_DEFAULT:
        return []
    return default


def _build_support_triage_item_summary(
    item: dict[str, object] | None,
    fields: tuple[tuple[object, ...], ...],
) -> dict[str, object]:
    return {
        str(output_key): _support_triage_summary_value(
            item,
            str(source_key),
            _support_triage_field_default(field),
        )
        for field in fields
        for output_key, source_key in [field[:2]]
    }


_SUPPORT_TRIAGE_APPLY_SUMMARY_SPECS: tuple[
    tuple[str, str, tuple[tuple[object, ...], ...]],
    ...,
] = (
    (
        "triage_apply_summary",
        "triage_apply_history",
        (
            ("top_audit_log_id", "audit_log_id"),
            ("top_actor_label", "actor_label"),
            ("top_pack_key", "pack_key"),
            ("top_pack_label", "pack_label"),
            ("top_route_key", "route_key"),
            ("top_route_label", "route_label"),
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_count", "count", 0),
            ("top_ticket_ids", "ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_created_at_label", "created_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_route_summary",
        "triage_apply_routes",
        (
            ("top_route_key", "route_key"),
            ("top_route_label", "route_label"),
            ("top_pack_key", "pack_key"),
            ("top_pack_label", "pack_label"),
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_actor_count", "actor_count", 0),
            ("top_actor_label", "top_actor_label"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_actor_summary",
        "triage_apply_actors",
        (
            ("top_actor_user_id", "actor_user_id"),
            ("top_actor_label", "actor_label"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_route_count", "route_count", 0),
            ("top_route_key", "top_route_key"),
            ("top_route_label", "top_route_label"),
            ("top_reply_key", "top_reply_key"),
            ("top_reply_title", "top_reply_title"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_reply_summary",
        "triage_apply_replies",
        (
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_actor_count", "actor_count", 0),
            ("top_route_count", "route_count", 0),
            ("top_actor_label", "top_actor_label"),
            ("top_route_key", "top_route_key"),
            ("top_route_label", "top_route_label"),
            ("top_pack_key", "top_pack_key"),
            ("top_pack_label", "top_pack_label"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_actor_reply_summary",
        "triage_apply_actor_replies",
        (
            ("top_actor_user_id", "actor_user_id"),
            ("top_actor_label", "actor_label"),
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_route_count", "route_count", 0),
            ("top_route_key", "top_route_key"),
            ("top_route_label", "top_route_label"),
            ("top_pack_key", "top_pack_key"),
            ("top_pack_label", "top_pack_label"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_route_actor_summary",
        "triage_apply_route_actors",
        (
            ("top_route_key", "route_key"),
            ("top_route_label", "route_label"),
            ("top_actor_user_id", "actor_user_id"),
            ("top_actor_label", "actor_label"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_reply_count", "reply_count", 0),
            ("top_reply_key", "top_reply_key"),
            ("top_reply_title", "top_reply_title"),
            ("top_pack_key", "top_pack_key"),
            ("top_pack_label", "top_pack_label"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_reply_pack_summary",
        "triage_apply_reply_packs",
        (
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_pack_key", "pack_key"),
            ("top_pack_label", "pack_label"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_actor_count", "actor_count", 0),
            ("top_actor_label", "top_actor_label"),
            ("top_route_key", "top_route_key"),
            ("top_route_label", "top_route_label"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_route_reply_actor_summary",
        "triage_apply_route_reply_actors",
        (
            ("top_route_key", "route_key"),
            ("top_route_label", "route_label"),
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_actor_user_id", "actor_user_id"),
            ("top_actor_label", "actor_label"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_pack_key", "top_pack_key"),
            ("top_pack_label", "top_pack_label"),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_focus_summary",
        "triage_apply_focus",
        (
            ("top_key", "key"),
            ("top_source_key", "source_key"),
            ("top_source_label", "source_label"),
            ("top_title", "title"),
            ("top_secondary_label", "secondary_label"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_focus_score", "focus_score", 0),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
    (
        "triage_apply_effectiveness_summary",
        "triage_apply_effectiveness",
        (
            ("top_key", "key"),
            ("top_source_key", "source_key"),
            ("top_source_label", "source_label"),
            ("top_title", "title"),
            ("top_secondary_label", "secondary_label"),
            ("top_route_key", "route_key"),
            ("top_route_label", "route_label"),
            ("top_reply_key", "reply_key"),
            ("top_reply_title", "reply_title"),
            ("top_actor_user_id", "actor_user_id"),
            ("top_actor_label", "actor_label"),
            ("top_pack_key", "pack_key"),
            ("top_pack_label", "pack_label"),
            ("top_apply_count", "apply_count", 0),
            ("top_ticket_count", "ticket_count", 0),
            ("top_coverage_count", "coverage_count", 0),
            ("top_coverage_label", "coverage_label"),
            ("top_effectiveness_score", "effectiveness_score", 0),
            ("top_sample_ticket_ids", "sample_ticket_ids", _EMPTY_LIST_DEFAULT),
            ("top_latest_applied_at_label", "latest_applied_at_label"),
            ("top_note", "note"),
        ),
    ),
)


def _build_support_triage_apply_summary_views(
    triage_views: dict[str, list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    return {
        summary_key: _build_support_triage_item_summary(
            _first_support_triage_item(triage_views[source_key]),
            fields,
        )
        for summary_key, source_key, fields in _SUPPORT_TRIAGE_APPLY_SUMMARY_SPECS
    }
