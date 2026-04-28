from aiogram import Router

from app.bot.routers.admin.channels import router as admin_channels_router
from app.bot.routers.admin.dashboard import router as admin_router
from app.bot.routers.admin.tariffs import router as admin_tariffs_router
from app.bot.routers.user.start import router as user_router


def get_routers() -> tuple[Router, ...]:
    return (user_router, admin_channels_router, admin_tariffs_router, admin_router)