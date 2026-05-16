from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.db.models import SupportMessage, SupportTicket


@dataclass(slots=True)
class SupportUserDashboard:
    open_ticket: SupportTicket | None
    recent_tickets: list[SupportTicket]
    open_count: int
    closed_count: int


@dataclass(slots=True)
class SupportInsightPackOutcome:
    pack_key: str
    ticket_count: int
    resolved_count: int
    no_response_count: int
    duplicate_count: int
    other_count: int
    resolved_rate_percent: float
    no_response_rate_percent: float
    duplicate_rate_percent: float


@dataclass(slots=True)
class SupportCloseReasonTrend:
    reason: str
    current_count: int
    previous_count: int
    delta: int


@dataclass(slots=True)
class SupportSlaHotspot:
    kind: str
    category: str
    priority: str
    count: int


@dataclass(slots=True)
class SupportSlaAction:
    kind: str
    category: str
    priority: str
    count: int
    action_key: str
    escalation_key: str
    note: str


@dataclass(slots=True)
class SupportSlaActionQueue:
    key: str
    sample_ticket_ids: tuple[int, ...]
    count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_kind: str | None
    top_priority: str | None
    top_category: str | None
    top_escalation_lane: str | None
    note: str


@dataclass(slots=True)
class SupportActionLane:
    key: str
    count: int
    high_priority_count: int
    stale_count: int
    sla_warning_count: int
    sla_breach_count: int
    top_category: str | None


@dataclass(slots=True)
class SupportNextActionQueue:
    key: str
    sample_ticket_ids: tuple[int, ...]
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_category: str | None
    top_escalation_lane: str | None
    note: str


@dataclass(slots=True)
class SupportActionRoute:
    key: str
    escalation_key: str
    action_key: str
    sample_ticket_ids: tuple[int, ...]
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    high_priority_count: int
    stale_count: int
    sla_warning_count: int
    sla_breach_count: int
    top_priority: str | None
    top_category: str | None
    top_kind: str | None
    note: str


@dataclass(slots=True)
class SupportTriageQueueItem:
    key: str
    escalation_key: str
    action_key: str
    pack_key: str
    sample_ticket_ids: tuple[int, ...]
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    high_priority_count: int
    stale_count: int
    sla_warning_count: int
    sla_breach_count: int
    top_priority: str | None
    top_kind: str | None
    note: str


@dataclass(slots=True)
class SupportEscalationLane:
    key: str
    count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_category: str | None


@dataclass(slots=True)
class SupportEscalationAction:
    key: str
    escalation_key: str
    action_key: str
    count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_category: str | None


@dataclass(slots=True)
class SupportPriorityFocus:
    key: str
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    stale_count: int
    sla_warning_count: int
    sla_breach_count: int
    top_category: str | None
    top_action_lane: str | None
    top_escalation_lane: str | None


@dataclass(slots=True)
class SupportEscalationWatch:
    key: str
    count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    high_priority_count: int
    stale_count: int
    sla_breach_count: int
    top_priority: str | None
    top_category: str | None
    top_action_lane: str | None
    watch_score: int
    note: str


@dataclass(slots=True)
class SupportEscalationTrend:
    key: str
    current_count: int
    previous_count: int
    delta: int


@dataclass(slots=True)
class SupportOperatorActionTrend:
    key: str
    pack_key: str
    close_reason: str
    action_key: str
    current_count: int
    previous_count: int
    delta: int
    note: str


@dataclass(slots=True)
class SupportTriageApplyHistory:
    audit_log_id: int
    actor_user_id: int | None
    actor_label: str | None
    triage_key: str
    pack_key: str
    route_key: str
    reply_key: str
    reply_title: str | None
    ticket_ids: tuple[int, ...]
    count: int
    created_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyRoute:
    key: str
    route_key: str
    pack_key: str
    reply_key: str
    reply_title: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    actor_count: int
    top_actor_label: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyActor:
    actor_user_id: int | None
    actor_label: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    route_count: int
    top_route_key: str | None
    top_reply_key: str | None
    top_reply_title: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyReply:
    reply_key: str
    reply_title: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    actor_count: int
    route_count: int
    top_actor_label: str | None
    top_route_key: str | None
    top_pack_key: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyActorReply:
    actor_user_id: int | None
    actor_label: str | None
    reply_key: str
    reply_title: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    route_count: int
    top_route_key: str | None
    top_pack_key: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyRouteActor:
    route_key: str
    actor_user_id: int | None
    actor_label: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    reply_count: int
    top_reply_key: str | None
    top_reply_title: str | None
    top_pack_key: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyReplyPack:
    reply_key: str
    reply_title: str | None
    pack_key: str
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    actor_count: int
    top_actor_label: str | None
    top_route_key: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyRouteReplyActor:
    route_key: str
    reply_key: str
    reply_title: str | None
    actor_user_id: int | None
    actor_label: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    top_pack_key: str | None
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyFocus:
    key: str
    source_key: str
    source_label: str
    title: str
    secondary_label: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    focus_score: int
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportTriageApplyEffectiveness:
    key: str
    source_key: str
    source_label: str
    title: str
    secondary_label: str | None
    route_key: str | None
    reply_key: str | None
    reply_title: str | None
    actor_user_id: int | None
    actor_label: str | None
    pack_key: str | None
    sample_ticket_ids: tuple[int, ...]
    apply_count: int
    ticket_count: int
    coverage_count: int
    effectiveness_score: int
    latest_applied_at: datetime
    note: str


@dataclass(slots=True)
class SupportInsights:
    priority_counts: dict[str, int]
    waiting_state_counts: dict[str, int]
    category_counts: dict[str, int]
    canned_reply_pack_counts: dict[str, int]
    recent_close_reason_counts: dict[str, int]
    previous_close_reason_counts: dict[str, int]
    recent_close_total: int
    previous_close_total: int
    recent_close_days: int
    pack_outcome_days: int
    canned_reply_pack_outcomes: list[SupportInsightPackOutcome]
    close_reason_trends: list[SupportCloseReasonTrend]
    sla_hotspots: list[SupportSlaHotspot]
    sla_actions: list[SupportSlaAction]
    sla_action_queue: list[SupportSlaActionQueue]
    action_lanes: list[SupportActionLane]
    next_action_queue: list[SupportNextActionQueue]
    action_routes: list[SupportActionRoute]
    triage_queue: list[SupportTriageQueueItem]
    escalation_lanes: list[SupportEscalationLane]
    escalation_actions: list[SupportEscalationAction]
    priority_focus: list[SupportPriorityFocus]
    escalation_watchlist: list[SupportEscalationWatch]
    operator_action_trends: list[SupportOperatorActionTrend]
    escalation_trends: list[SupportEscalationTrend]
    triage_apply_history: list[SupportTriageApplyHistory] = field(default_factory=list)
    triage_apply_routes: list[SupportTriageApplyRoute] = field(default_factory=list)
    triage_apply_actors: list[SupportTriageApplyActor] = field(default_factory=list)
    triage_apply_replies: list[SupportTriageApplyReply] = field(default_factory=list)
    triage_apply_actor_replies: list[SupportTriageApplyActorReply] = field(
        default_factory=list
    )
    triage_apply_route_actors: list[SupportTriageApplyRouteActor] = field(
        default_factory=list
    )
    triage_apply_reply_packs: list[SupportTriageApplyReplyPack] = field(
        default_factory=list
    )
    triage_apply_route_reply_actors: list[SupportTriageApplyRouteReplyActor] = field(
        default_factory=list
    )
    triage_apply_focus: list[SupportTriageApplyFocus] = field(default_factory=list)
    triage_apply_effectiveness: list[SupportTriageApplyEffectiveness] = field(
        default_factory=list
    )


@dataclass(slots=True)
class SupportAdminInbox:
    status: str
    tickets: list[SupportTicket]
    open_count: int
    closed_count: int
    awaiting_admin_count: int
    awaiting_user_count: int
    stale_open_count: int
    high_priority_open_count: int
    sla_warning_count: int
    sla_breach_count: int
    close_reason_counts: dict[str, int]
    insights: SupportInsights


@dataclass(slots=True)
class SupportTicketThread:
    ticket: SupportTicket
    messages: list[SupportMessage]


@dataclass(slots=True)
class SupportCannedReply:
    key: str
    title: str
    body: str
    kind: str
