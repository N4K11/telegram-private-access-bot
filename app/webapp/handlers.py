from __future__ import annotations

import json
import logging
from pathlib import Path

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repositories.users import UserRepository
from app.services.admin_roles import (
    PERMISSION_ADMIN_PANEL,
    PERMISSION_DIAGNOSTICS,
    PERMISSION_PAYMENTS,
    PERMISSION_SUPPORT,
    PERMISSION_USERS_VIEW,
    has_permission,
    is_admin_role,
)
from app.services.observability import EVENT_CABINET_AUTH_FAILED
from app.services.web_admin_dashboard import (
    build_web_admin_dashboard_payload,
    build_web_admin_payments_payload,
    build_web_admin_support_payload,
    build_web_admin_support_ticket_payload,
    build_web_admin_users_payload,
    run_web_admin_channel_check_action,
)
from app.services.web_auth import (
    WebAppAuthError,
    WebAppIdentity,
    validate_telegram_webapp_init_data,
)
from app.services.web_cabinet import (
    build_cabinet_admin_summary_payload,
    build_cabinet_bootstrap_payload,
    build_cabinet_profile_payload,
)
from app.webhook.app_keys import BOT_APP_KEY, SESSION_FACTORY_APP_KEY, SETTINGS_APP_KEY

INIT_DATA_HEADER = "X-Telegram-Init-Data"
MINI_APP_HTML_FILE = Path(__file__).resolve().parents[2] / "web" / "app" / "index.html"
logger = logging.getLogger(__name__)


def register_webapp_routes(app: web.Application, settings: Settings) -> None:
    base_path = settings.mini_app_path.rstrip("/") or settings.mini_app_path
    app.router.add_get(base_path, mini_app_page)
    if base_path != "/":
        app.router.add_get(f"{base_path}/", mini_app_page)
    app.router.add_post(f"{base_path}/api/auth", mini_app_auth)
    app.router.add_get(f"{base_path}/api/bootstrap", mini_app_bootstrap)
    app.router.add_get(f"{base_path}/api/users/{{telegram_id}}/profile", mini_app_user_profile)
    app.router.add_get(f"{base_path}/api/admin/summary", mini_app_admin_summary)
    app.router.add_get(f"{base_path}/api/admin/dashboard", mini_app_admin_dashboard)
    app.router.add_get(f"{base_path}/api/admin/users", mini_app_admin_users)
    app.router.add_get(f"{base_path}/api/admin/payments", mini_app_admin_payments)
    app.router.add_get(f"{base_path}/api/admin/support", mini_app_admin_support)
    app.router.add_get(
        f"{base_path}/api/admin/support/{{ticket_id}}",
        mini_app_admin_support_ticket,
    )
    app.router.add_post(
        f"{base_path}/api/admin/actions/channel-check",
        mini_app_admin_channel_check,
    )


async def mini_app_page(request: web.Request) -> web.Response:
    if not MINI_APP_HTML_FILE.exists():
        return web.Response(text="Mini App is not available.", status=503)
    return web.Response(
        text=MINI_APP_HTML_FILE.read_text(encoding="utf-8"),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


async def mini_app_auth(request: web.Request) -> web.Response:
    payload = await _read_json_body(request)
    if payload is None:
        return web.json_response({"ok": False, "error": "invalid_request"}, status=400)
    init_data = str(payload.get("init_data") or payload.get("initData") or "")
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    async with session_factory() as session:
        auth_result = await _authenticate_session(
            session,
            settings=request.app[SETTINGS_APP_KEY],
            init_data=init_data,
        )
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        identity, user = auth_result
        await session.commit()
    return web.json_response(
        {
            "ok": True,
            "user": {
                "telegram_id": identity.telegram_id,
                "username": identity.username,
                "first_name": identity.first_name,
                "last_name": identity.last_name,
                "language_code": identity.language_code,
                "is_admin": bool(user.is_admin),
                "role": user.role,
            },
        }
    )


async def mini_app_bootstrap(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        data = await build_cabinet_bootstrap_payload(session, user=user, settings=settings)
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def mini_app_user_profile(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    try:
        requested_telegram_id = int(request.match_info["telegram_id"])
    except (KeyError, TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid_user"}, status=400)
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        if requested_telegram_id != user.telegram_id and not user.is_admin:
            await session.commit()
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)
        data = await build_cabinet_profile_payload(
            session,
            telegram_user_id=requested_telegram_id,
            settings=settings,
        )
        await session.commit()
    if data is None:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_summary(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        if not user.is_admin:
            await session.commit()
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)
        data = await build_cabinet_admin_summary_payload(session, settings=settings)
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_dashboard(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        denied = _require_permission(user, PERMISSION_ADMIN_PANEL)
        if denied is not None:
            await session.commit()
            return denied
        data = await build_web_admin_dashboard_payload(
            session,
            settings=settings,
            viewer_role=user.role,
        )
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_users(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        denied = _require_permission(user, PERMISSION_USERS_VIEW)
        if denied is not None:
            await session.commit()
            return denied
        data = await build_web_admin_users_payload(
            session,
            settings=settings,
            viewer_role=user.role,
            filter_key=request.query.get("filter", "all"),
            query=request.query.get("query"),
            page=_positive_int(request.query.get("page"), 1),
            page_size=_positive_int(request.query.get("page_size"), 8),
        )
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_payments(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        denied = _require_permission(user, PERMISSION_PAYMENTS)
        if denied is not None:
            await session.commit()
            return denied
        data = await build_web_admin_payments_payload(
            session,
            settings=settings,
            viewer_role=user.role,
            provider_filter=request.query.get("provider", "all"),
            query=request.query.get("query"),
            page=_positive_int(request.query.get("page"), 1),
            page_size=_positive_int(request.query.get("page_size"), 8),
        )
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_support(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        denied = _require_permission(user, PERMISSION_SUPPORT)
        if denied is not None:
            await session.commit()
            return denied
        data = await build_web_admin_support_payload(
            session,
            settings=settings,
            viewer_role=user.role,
            status=request.query.get("status", "open"),
            queue=request.query.get("queue", "all"),
            query=request.query.get("query"),
            page=_positive_int(request.query.get("page"), 1),
            page_size=_positive_int(request.query.get("page_size"), 8),
        )
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_support_ticket(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    try:
        ticket_id = int(request.match_info["ticket_id"])
    except (KeyError, TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid_ticket"}, status=400)
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        denied = _require_permission(user, PERMISSION_SUPPORT)
        if denied is not None:
            await session.commit()
            return denied
        data = await build_web_admin_support_ticket_payload(
            session,
            settings=settings,
            viewer_role=user.role,
            ticket_id=ticket_id,
        )
        await session.commit()
    if data is None:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)
    return web.json_response({"ok": True, "data": data})


async def mini_app_admin_channel_check(request: web.Request) -> web.Response:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    settings = request.app[SETTINGS_APP_KEY]
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    bot = request.app[BOT_APP_KEY]
    async with session_factory() as session:
        auth_result = await _authenticate_session(session, settings=settings, init_data=init_data)
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        denied = _require_permission(user, PERMISSION_DIAGNOSTICS)
        if denied is not None:
            await session.commit()
            return denied
        data = await run_web_admin_channel_check_action(
            session,
            bot=bot,
            settings=settings,
            actor_user_id=user.id,
        )
        await session.commit()
    return web.json_response({"ok": True, "data": data})


async def _authenticate_session(
    session: AsyncSession,
    *,
    settings: Settings,
    init_data: str,
) -> tuple[WebAppIdentity, object] | web.Response:
    token = settings.bot_token.get_secret_value() if settings.bot_token is not None else ""
    if not token:
        return web.json_response({"ok": False, "error": "service_unavailable"}, status=503)
    try:
        identity = validate_telegram_webapp_init_data(
            init_data,
            bot_token=token,
            max_age_seconds=settings.mini_app_auth_max_age_seconds,
        )
    except WebAppAuthError as exc:
        logger.error(
            "Mini App auth failed: %s",
            exc,
            extra={"event_name": EVENT_CABINET_AUTH_FAILED},
        )
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    user = await UserRepository(session).upsert_from_identity(
        telegram_id=identity.telegram_id,
        username=identity.username,
        first_name=identity.first_name,
        last_name=identity.last_name,
        language_code=identity.language_code,
        admin_ids=settings.admin_ids_set,
    )
    await session.flush()
    return identity, user


async def _read_json_body(request: web.Request) -> dict[str, object] | None:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _get_session_factory(request: web.Request) -> async_sessionmaker[AsyncSession] | None:
    return request.app.get(SESSION_FACTORY_APP_KEY)


def _require_permission(user, permission: str) -> web.Response | None:
    if not is_admin_role(user.role):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)
    if not has_permission(user.role, permission):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)
    return None


def _positive_int(raw_value: str | None, default: int) -> int:
    try:
        value = int(raw_value or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default