from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsDailyFact, LifecycleCampaignFact, SupportQueueFact
from app.services.admin_read_models import ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS
from app.services.web_admin_dashboard_read_model_descriptors import (
    READ_MODEL_GROUP_ANALYTICS,
    READ_MODEL_GROUP_LIFECYCLE,
    READ_MODEL_GROUP_SUPPORT,
    ReadModelDescriptor,
)
from app.services.web_admin_dashboard_read_model_serializers import _decode_payload


async def _load_snapshot_payload_lookups(
    session: AsyncSession,
    *,
    descriptors: list[ReadModelDescriptor],
    fact_date: datetime,
) -> tuple[
    dict[tuple[str, str], tuple[dict[str, object], datetime]],
    dict[str, tuple[dict[str, object], datetime]],
    dict[str, tuple[dict[str, object], datetime]],
]:
    analytics_rows = (
        await session.execute(
            select(AnalyticsDailyFact).where(
                AnalyticsDailyFact.fact_date == fact_date.date(),
                AnalyticsDailyFact.fact_key.in_(
                    {
                        descriptor.storage_key
                        for descriptor in descriptors
                        if descriptor.storage_group == READ_MODEL_GROUP_ANALYTICS
                    }
                ),
            )
        )
    ).scalars()
    lifecycle_rows = (
        await session.execute(
            select(LifecycleCampaignFact).where(
                LifecycleCampaignFact.view_key.in_(
                    {
                        descriptor.storage_key
                        for descriptor in descriptors
                        if descriptor.storage_group == READ_MODEL_GROUP_LIFECYCLE
                    }
                )
            )
        )
    ).scalars()
    support_rows = (
        await session.execute(
            select(SupportQueueFact).where(
                SupportQueueFact.view_key.in_(
                    {
                        descriptor.storage_key
                        for descriptor in descriptors
                        if descriptor.storage_group == READ_MODEL_GROUP_SUPPORT
                    }
                )
            )
        )
    ).scalars()

    analytics_lookup = {
        (row.fact_key, row.scope_key): (_decode_payload(row.payload), row.generated_at)
        for row in analytics_rows
        if row.fact_key != ANALYTICS_FACT_KEY_WEB_ADMIN_READ_MODELS
    }
    lifecycle_lookup = {
        row.view_key: (_decode_payload(row.payload), row.generated_at) for row in lifecycle_rows
    }
    support_lookup = {
        row.view_key: (_decode_payload(row.payload), row.generated_at) for row in support_rows
    }
    return analytics_lookup, lifecycle_lookup, support_lookup


def _lookup_descriptor_snapshot(
    descriptor: ReadModelDescriptor,
    *,
    analytics_lookup: dict[tuple[str, str], tuple[dict[str, object], datetime]],
    lifecycle_lookup: dict[str, tuple[dict[str, object], datetime]],
    support_lookup: dict[str, tuple[dict[str, object], datetime]],
) -> tuple[dict[str, object] | None, datetime | None]:
    if descriptor.storage_group == READ_MODEL_GROUP_ANALYTICS:
        return analytics_lookup.get(
            (descriptor.storage_key, descriptor.scope_key or "all"),
            (None, None),
        )
    if descriptor.storage_group == READ_MODEL_GROUP_LIFECYCLE:
        return lifecycle_lookup.get(descriptor.storage_key, (None, None))
    return support_lookup.get(descriptor.storage_key, (None, None))
