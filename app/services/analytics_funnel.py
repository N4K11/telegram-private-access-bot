from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, InviteLink
from app.services.analytics_common import _audit_targets_by_channel, _parse_payload
from app.services.analytics_models import ConversionSourceSnapshot, ProductFunnelSnapshot
from app.services.conversion import conversion_source_label, normalize_conversion_source


async def _build_product_funnel(
    session: AsyncSession,
    *,
    channel_titles: dict[int, str],
    tariff_channel_map: dict[int, int],
    paid_rows: list[tuple[int, str, int, datetime | None, int | None]],
) -> tuple[ProductFunnelSnapshot, ...]:
    buy_viewed_by_channel = await _audit_targets_by_channel(
        session,
        actions=("buy_screen_viewed",),
        tariff_channel_map=tariff_channel_map,
    )
    product_selected_by_channel = await _audit_targets_by_channel(
        session,
        actions=("product_selected",),
        tariff_channel_map=tariff_channel_map,
    )
    tariff_opened_by_channel = await _audit_targets_by_channel(
        session,
        actions=("tariff_detail_opened",),
        tariff_channel_map=tariff_channel_map,
    )
    offer_clicked_by_channel = await _audit_targets_by_channel(
        session,
        actions=("offer_clicked",),
        tariff_channel_map=tariff_channel_map,
    )
    invoice_created_by_channel = await _audit_targets_by_channel(
        session,
        actions=("invoice_created_stars", "invoice_created_crypto"),
        tariff_channel_map=tariff_channel_map,
    )
    repeat_purchase_by_channel = await _audit_targets_by_channel(
        session,
        actions=("repeat_purchase_paid",),
        tariff_channel_map=tariff_channel_map,
    )

    paid_by_channel: dict[int, set[int]] = defaultdict(set)
    revenue_by_channel: dict[int, int] = defaultdict(int)
    for user_id, _provider, amount, _paid_at, channel_id in paid_rows:
        if channel_id is None:
            continue
        paid_by_channel[channel_id].add(user_id)
        revenue_by_channel[channel_id] += int(amount)

    invite_by_channel: dict[int, set[int]] = defaultdict(set)
    invite_rows = list(
        (
            await session.execute(
                select(InviteLink.channel_id, InviteLink.user_id)
            )
        ).all()
    )
    for channel_id, user_id in invite_rows:
        invite_by_channel[int(channel_id)].add(int(user_id))

    all_channel_ids = set(channel_titles)
    all_channel_ids.update(buy_viewed_by_channel)
    all_channel_ids.update(product_selected_by_channel)
    all_channel_ids.update(tariff_opened_by_channel)
    all_channel_ids.update(offer_clicked_by_channel)
    all_channel_ids.update(invoice_created_by_channel)
    all_channel_ids.update(paid_by_channel)
    all_channel_ids.update(invite_by_channel)
    all_channel_ids.update(repeat_purchase_by_channel)

    items: list[ProductFunnelSnapshot] = []
    for channel_id in sorted(
        all_channel_ids,
        key=lambda item: (-revenue_by_channel.get(item, 0), channel_titles.get(item, ""), item),
    ):
        items.append(
            ProductFunnelSnapshot(
                channel_id=channel_id,
                channel_title=channel_titles.get(channel_id, f"????? #{channel_id}"),
                buy_viewed_users=len(buy_viewed_by_channel.get(channel_id, set())),
                product_selected_users=len(product_selected_by_channel.get(channel_id, set())),
                tariff_opened_users=len(tariff_opened_by_channel.get(channel_id, set())),
                offer_clicked_users=len(offer_clicked_by_channel.get(channel_id, set())),
                invoice_created_users=len(invoice_created_by_channel.get(channel_id, set())),
                paid_users=len(paid_by_channel.get(channel_id, set())),
                invite_issued_users=len(invite_by_channel.get(channel_id, set())),
                repeat_purchase_users=len(repeat_purchase_by_channel.get(channel_id, set())),
                revenue_total=revenue_by_channel.get(channel_id, 0),
            )
        )
    return tuple(items)


async def _build_source_funnel(session: AsyncSession) -> tuple[ConversionSourceSnapshot, ...]:
    action_map = {
        "buy_screen_viewed": "buy_viewed_users",
        "product_selected": "product_selected_users",
        "tariff_detail_opened": "tariff_opened_users",
        "offer_clicked": "offer_clicked_users",
        "invoice_created_stars": "invoice_created_users",
        "invoice_created_crypto": "invoice_created_users",
        "payment_paid_stars": "paid_users",
        "payment_paid_crypto": "paid_users",
        "invite_issued": "invite_issued_users",
    }
    result = await session.execute(
        select(AuditLog.action, AuditLog.target_user_id, AuditLog.payload).where(
            AuditLog.action.in_(tuple(action_map))
        )
    )
    grouped: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for action, target_user_id, raw_payload in result.all():
        if target_user_id is None:
            continue
        payload = _parse_payload(raw_payload)
        source = normalize_conversion_source(payload.get("source"))
        if source is None:
            continue
        grouped[source][action_map[action]].add(int(target_user_id))

    items: list[ConversionSourceSnapshot] = []
    for source, metrics in grouped.items():
        items.append(
            ConversionSourceSnapshot(
                source=source,
                label=conversion_source_label(source),
                buy_viewed_users=len(metrics.get("buy_viewed_users", set())),
                product_selected_users=len(metrics.get("product_selected_users", set())),
                tariff_opened_users=len(metrics.get("tariff_opened_users", set())),
                offer_clicked_users=len(metrics.get("offer_clicked_users", set())),
                invoice_created_users=len(metrics.get("invoice_created_users", set())),
                paid_users=len(metrics.get("paid_users", set())),
                invite_issued_users=len(metrics.get("invite_issued_users", set())),
            )
        )
    items.sort(
        key=lambda item: (
            -item.paid_users,
            -item.invoice_created_users,
            -item.buy_viewed_users,
            item.label,
        )
    )
    return tuple(items)


