from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdminReadModelAlertSummary:
    source: str
    generated_at_label: str | None
    staleness_seconds: int
    tracked_count: int
    available_count: int
    missing_count: int
    stale_count: int
    budget_exceeded_count: int
    alert_count: int
    top_attention_label: str | None
    top_attention_status_label: str | None
    top_attention_note: str | None

    @property
    def has_alerts(self) -> bool:
        return self.alert_count > 0


@dataclass(frozen=True, slots=True)
class AdminReadModelDriftSummary:
    source: str
    generated_at_label: str | None
    staleness_seconds: int
    compared_count: int
    missing_snapshot_count: int
    regression_count: int
    improvement_count: int
    budget_regression_count: int
    query_regression_count: int
    payload_regression_count: int
    build_regression_count: int
    top_regression_label: str | None
    top_regression_note: str | None
    top_budget_regression_label: str | None
    top_query_regression_label: str | None
    top_payload_regression_label: str | None
    top_build_regression_label: str | None
    top_items: tuple[AdminReadModelDriftItemSummary, ...] = ()

    @property
    def has_regressions(self) -> bool:
        return self.regression_count > 0 or self.budget_regression_count > 0


@dataclass(frozen=True, slots=True)
class AdminReadModelDriftItemSummary:
    label: str
    note: str | None
    query_count_delta: int
    payload_bytes_delta: int
    build_duration_ms_delta: int
    budget_regressed: bool


@dataclass(frozen=True, slots=True)
class AdminReadModelActionSummary:
    source: str
    generated_at_label: str | None
    staleness_seconds: int
    tracked_count: int
    surface_count: int
    alert_item_count: int
    snapshot_action_count: int
    budget_action_count: int
    drift_action_count: int
    top_action_label: str | None
    top_action_note: str | None
    top_budget_action_label: str | None
    top_drift_action_label: str | None
    top_items: tuple[AdminReadModelActionItemSummary, ...] = ()

    @property
    def has_actions(self) -> bool:
        return self.surface_count > 0


@dataclass(frozen=True, slots=True)
class AdminReadModelActionItemSummary:
    label: str
    action_label: str | None
    action_note: str | None
    issue_summary_label: str | None
    action_category_label: str | None


@dataclass(frozen=True, slots=True)
class AdminReadModelWatchItemSummary:
    label: str
    watch_kind_label: str | None
    source_mode_label: str | None
    note: str | None
    status_label: str | None


@dataclass(frozen=True, slots=True)
class AdminReadModelWatchlistSummary:
    source: str
    generated_at_label: str | None
    staleness_seconds: int
    tracked_count: int
    alert_item_count: int
    missing_count: int
    stale_count: int
    budget_exceeded_count: int
    regression_count: int
    top_attention_label: str | None
    top_attention_kind_label: str | None
    top_attention_note: str | None
    top_regression_label: str | None
    top_budget_label: str | None
    top_items: tuple[AdminReadModelWatchItemSummary, ...] = ()

    @property
    def has_alerts(self) -> bool:
        return self.alert_item_count > 0


@dataclass(frozen=True, slots=True)
class AdminReadModelActionDigest:
    summary_line: str
    top_label: str | None
    top_detail: str | None
    item_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminReadModelWatchlistDigest:
    summary_line: str
    top_label: str | None
    top_detail: str | None
    item_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminReadModelDriftDigest:
    summary_line: str
    extended_summary_line: str
    top_label: str | None
    top_detail: str | None
    item_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminReadModelFocusSummary:
    kind: str
    kind_label: str
    label: str
    detail: str | None

    @property
    def line(self) -> str:
        if self.detail:
            return f"{self.kind_label} · {self.label} · {self.detail}"
        return f"{self.kind_label} · {self.label}"


@dataclass(frozen=True, slots=True)
class AdminReadModelOperatorDigest:
    summary_line: str
    focus_line: str | None
    watch_line: str | None
    action_line: str | None
    drift_line: str | None
