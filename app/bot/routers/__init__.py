# ruff: noqa: I001
from aiogram import Router

from app.bot.routers.admin.analytics import router as admin_analytics_router
from app.bot.routers.admin.audit import router as admin_audit_router
from app.bot.routers.admin.backups import router as admin_backups_router
from app.bot.routers.admin.broadcasts import router as admin_broadcasts_router
from app.bot.routers.admin.channels import router as admin_channels_router
from app.bot.routers.admin.crypto import router as admin_crypto_router
from app.bot.routers.admin.dashboard import router as admin_router
from app.bot.routers.admin.diagnostics import router as admin_diagnostics_router
from app.bot.routers.admin.finance import router as admin_finance_router
from app.bot.routers.admin.health import router as admin_health_router
from app.bot.routers.admin.observability import router as admin_observability_router
from app.bot.routers.admin.promos import router as admin_promos_router
from app.bot.routers.admin.referrals import router as admin_referrals_router
from app.bot.routers.admin.roles import router as admin_roles_router
from app.bot.routers.admin.support import router as admin_support_router
from app.bot.routers.admin.tariffs import router as admin_tariffs_router
from app.bot.routers.admin.texts import router as admin_texts_router
from app.bot.routers.admin.users import router as admin_users_router
from app.bot.routers.user.cabinet import router as user_cabinet_router
from app.bot.routers.user.invites import router as user_invites_router
from app.bot.routers.user.legal import router as user_legal_router
from app.bot.routers.user.payments import router as user_payments_router
from app.bot.routers.user.profile import router as user_profile_router
from app.bot.routers.user.promos import router as user_promos_router
from app.bot.routers.user.referrals import router as user_referrals_router
from app.bot.routers.user.start import router as user_router
from app.bot.routers.user.support import router as user_support_router


def get_routers() -> tuple[Router, ...]:
    return (
        user_payments_router,
        user_promos_router,
        user_referrals_router,
        user_invites_router,
        user_profile_router,
        user_support_router,
        user_legal_router,
        user_cabinet_router,
        user_router,
        admin_analytics_router,
        admin_users_router,
        admin_support_router,
        admin_audit_router,
        admin_texts_router,
        admin_broadcasts_router,
        admin_backups_router,
        admin_channels_router,
        admin_tariffs_router,
        admin_diagnostics_router,
        admin_health_router,
        admin_observability_router,
        admin_promos_router,
        admin_roles_router,
        admin_referrals_router,
        admin_finance_router,
        admin_crypto_router,
        admin_router,
    )
