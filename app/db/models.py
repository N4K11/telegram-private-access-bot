from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    referral_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    referred_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    referred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referral_reward_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pending_referral_reward_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")
    payments: Mapped[list[Payment]] = relationship(back_populates="user")


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    invite_users_permission: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_users_permission: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tariffs: Mapped[list[Tariff]] = relationship(back_populates="channel")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="channel")


class Tariff(TimestampMixin, Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    badge: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offer_copy: Mapped[str | None] = mapped_column(String(160), nullable=True)
    offer_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offer_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lifetime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default_offer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    price_crypto: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    crypto_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    crypto_asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)

    channel: Mapped[Channel] = relationship(back_populates="tariffs")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="tariff")
    payments: Mapped[list[Payment]] = relationship(back_populates="tariff")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="purchase", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    warning_3d_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    warning_1d_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_notice_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    grace_revoke_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")
    tariff: Mapped[Tariff] = relationship(back_populates="subscriptions")
    channel: Mapped[Channel] = relationship(back_populates="subscriptions")
    invite_links: Mapped[list[InviteLink]] = relationship(back_populates="subscription")


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index(
            "ix_payments_status_paid_at_user_id_channel_id",
            "status",
            "paid_at",
            "user_id",
            "channel_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_payload: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    user: Mapped[User] = relationship(back_populates="payments")
    tariff: Mapped[Tariff | None] = relationship(back_populates="payments")


class InviteLink(TimestampMixin, Base):
    __tablename__ = "invite_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), nullable=False)
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    member_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    subscription: Mapped[Subscription] = relationship(back_populates="invite_links")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index(
            "ix_audit_logs_action_created_at_target_user_id",
            "action",
            "created_at",
            "target_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TextTemplate(TimestampMixin, Base):
    __tablename__ = "text_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class BroadcastCampaign(TimestampMixin, Base):
    __tablename__ = "broadcast_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    filter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    total_targets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_broadcast_delivery_campaign_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("broadcast_campaigns.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_to_admin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SupportTicket(TimestampMixin, Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index(
            "ix_support_tickets_status_priority_updated_at_user_id",
            "status",
            "priority",
            "updated_at",
            "user_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    close_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_user_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_admin_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    closed_by_user: Mapped[User | None] = relationship(foreign_keys=[closed_by_user_id])
    messages: Mapped[list[SupportMessage]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.id",
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id"),
        nullable=False,
        index=True,
    )
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship(foreign_keys=[sender_user_id])


class CryptoInvoice(TimestampMixin, Base):
    __tablename__ = "crypto_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"), nullable=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fiat_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    invoice_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)


class PromoCode(TimestampMixin, Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    promo_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_purchase_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    per_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    tariff: Mapped[Tariff | None] = relationship()
    redemptions: Mapped[list[PromoRedemption]] = relationship(back_populates="promo_code")


class PromoRedemption(TimestampMixin, Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(
        ForeignKey("promo_codes.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    applied_tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"), nullable=True)
    amount_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    promo_code: Mapped[PromoCode] = relationship(back_populates="redemptions")
    payment: Mapped[Payment | None] = relationship()
    tariff: Mapped[Tariff | None] = relationship()


class AnalyticsDailyFact(TimestampMixin, Base):
    __tablename__ = "analytics_daily_facts"
    __table_args__ = (
        UniqueConstraint(
            "fact_date",
            "fact_key",
            "scope_key",
            name="uq_analytics_daily_fact_scope",
        ),
        Index(
            "ix_analytics_daily_facts_fact_key_generated_at",
            "fact_key",
            "generated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fact_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fact_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(64), default="all", nullable=False)
    product_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"),
        nullable=True,
        index=True,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LifecycleCampaignFact(TimestampMixin, Base):
    __tablename__ = "lifecycle_campaign_facts"
    __table_args__ = (
        UniqueConstraint("view_key", name="uq_lifecycle_campaign_fact_view_key"),
        Index(
            "ix_lifecycle_campaign_facts_generated_at",
            "generated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    view_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SupportQueueFact(TimestampMixin, Base):
    __tablename__ = "support_queue_facts"
    __table_args__ = (
        UniqueConstraint("view_key", name="uq_support_queue_fact_view_key"),
        Index(
            "ix_support_queue_facts_generated_at",
            "generated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    view_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
