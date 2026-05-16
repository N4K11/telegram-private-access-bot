from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.services.admin_read_models import (
    ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT,
    ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
    ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
    ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
    ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
    PAYLOAD_BUDGET_ADMIN_ACQUISITION,
    PAYLOAD_BUDGET_ADMIN_CONVERSION,
    PAYLOAD_BUDGET_ADMIN_DASHBOARD,
    PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
    PAYLOAD_BUDGET_ADMIN_PRICING,
    PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
    PAYLOAD_BUDGET_ADMIN_SUMMARY,
    PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
    QUERY_BUDGET_ADMIN_ACQUISITION,
    QUERY_BUDGET_ADMIN_CONVERSION,
    QUERY_BUDGET_ADMIN_DASHBOARD,
    QUERY_BUDGET_ADMIN_LIFECYCLE,
    QUERY_BUDGET_ADMIN_PRICING,
    QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
    QUERY_BUDGET_ADMIN_SUMMARY,
    QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
)
from app.services.admin_roles import ADMIN_ROLES, ROLE_LABELS
from app.services.web_admin_dashboard_lifecycle_sections import LIFECYCLE_VIEWS
from app.services.web_admin_dashboard_support_sections import SUPPORT_INSIGHT_VIEWS

READ_MODEL_GROUP_ANALYTICS = "analytics"
READ_MODEL_GROUP_LIFECYCLE = "lifecycle"
READ_MODEL_GROUP_SUPPORT = "support"

@dataclass(frozen=True, slots=True)
class ReadModelDescriptor:
    storage_group: str
    storage_key: str
    label: str
    cadence_minutes: int
    query_budget: int | None
    payload_budget: int | None = None
    scope_key: str | None = None

    @property
    def identity(self) -> str:
        if self.scope_key:
            return f"{self.storage_group}:{self.storage_key}:{self.scope_key}"
        return f"{self.storage_group}:{self.storage_key}"


def _analytics_descriptors(settings: Settings) -> list[ReadModelDescriptor]:
    cadence_minutes = settings.admin_read_models_analytics_interval_minutes
    descriptors = [
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_CABINET_ADMIN_SUMMARY,
            label="Admin summary",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_SUMMARY,
            payload_budget=PAYLOAD_BUDGET_ADMIN_SUMMARY,
        ),
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_ADMIN_ANALYTICS_TEXT,
            label="Bot analytics text",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_SUMMARY,
            payload_budget=PAYLOAD_BUDGET_ADMIN_SUMMARY,
        ),
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_WEB_ADMIN_PRICING,
            label="Pricing / Offers",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_PRICING,
            payload_budget=PAYLOAD_BUDGET_ADMIN_PRICING,
        ),
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_WEB_ADMIN_ACQUISITION,
            label="Acquisition / Sources",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_ACQUISITION,
            payload_budget=PAYLOAD_BUDGET_ADMIN_ACQUISITION,
        ),
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_WEB_ADMIN_CONVERSION,
            label="Conversion / Products",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_CONVERSION,
            payload_budget=PAYLOAD_BUDGET_ADMIN_CONVERSION,
        ),
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_WEB_ADMIN_PROMO_REFERRAL,
            label="Promo / Referral",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_PROMO_REFERRAL,
            payload_budget=PAYLOAD_BUDGET_ADMIN_PROMO_REFERRAL,
        ),
    ]
    descriptors.extend(
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_ANALYTICS,
            storage_key=ANALYTICS_FACT_KEY_WEB_ADMIN_DASHBOARD,
            scope_key=f"role:{role}",
            label=f"Admin dashboard / {ROLE_LABELS.get(role, role.title())}",
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_DASHBOARD,
            payload_budget=PAYLOAD_BUDGET_ADMIN_DASHBOARD,
        )
        for role in ADMIN_ROLES
    )
    return descriptors


def _lifecycle_descriptors(settings: Settings) -> list[ReadModelDescriptor]:
    cadence_minutes = settings.admin_read_models_analytics_interval_minutes
    return [
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_LIFECYCLE,
            storage_key=view_key,
            label=label,
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_LIFECYCLE,
            payload_budget=PAYLOAD_BUDGET_ADMIN_LIFECYCLE,
        )
        for view_key, label in LIFECYCLE_VIEWS.items()
    ]


def _support_descriptors(settings: Settings) -> list[ReadModelDescriptor]:
    cadence_minutes = settings.admin_read_models_support_interval_minutes
    return [
        ReadModelDescriptor(
            storage_group=READ_MODEL_GROUP_SUPPORT,
            storage_key=view_key,
            label=label,
            cadence_minutes=cadence_minutes,
            query_budget=QUERY_BUDGET_ADMIN_SUPPORT_INSIGHTS,
            payload_budget=PAYLOAD_BUDGET_ADMIN_SUPPORT_INSIGHTS,
        )
        for view_key, label in SUPPORT_INSIGHT_VIEWS.items()
    ]

def _all_descriptors(settings: Settings) -> list[ReadModelDescriptor]:
    return (
        _analytics_descriptors(settings)
        + _lifecycle_descriptors(settings)
        + _support_descriptors(settings)
    )
