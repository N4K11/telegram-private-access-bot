from __future__ import annotations

import json
from pathlib import Path

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repositories.users import UserRepository
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
from app.webhook.app_keys import SESSION_FACTORY_APP_KEY, SETTINGS_APP_KEY

INIT_DATA_HEADER = "X-Telegram-Init-Data"
MINI_APP_HTML_FILE = Path(__file__).resolve().parents[2] / "web" / "app" / "index.html"


def register_webapp_routes(app: web.Application, settings: Settings) -> None:
    base_path = settings.mini_app_path.rstrip("/") or settings.mini_app_path
    app.router.add_get(base_path, mini_app_page)
    if base_path != "/":
        app.router.add_get(f"{base_path}/", mini_app_page)
    app.router.add_post(f"{base_path}/api/auth", mini_app_auth)
    app.router.add_get(f"{base_path}/api/bootstrap", mini_app_bootstrap)
    app.router.add_get(f"{base_path}/api/users/{{telegram_id}}/profile", mini_app_user_profile)
    app.router.add_get(f"{base_path}/api/admin/summary", mini_app_admin_summary)


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
        auth_result = await _authenticate_session(
            session,
            settings=settings,
            init_data=init_data,
        )
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        data = await build_cabinet_bootstrap_payload(
            session,
            user=user,
            settings=settings,
        )
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
        auth_result = await _authenticate_session(
            session,
            settings=settings,
            init_data=init_data,
        )
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
        auth_result = await _authenticate_session(
            session,
            settings=settings,
            init_data=init_data,
        )
        if isinstance(auth_result, web.Response):
            await session.rollback()
            return auth_result
        _, user = auth_result
        if not user.is_admin:
            await session.commit()
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)

        data = await build_cabinet_admin_summary_payload(
            session,
            settings=settings,
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
    except WebAppAuthError:
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
    except json.JSONDecodeError:
        return None
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _get_session_factory(
    request: web.Request,
) -> async_sessionmaker[AsyncSession] | None:
    return request.app.get(SESSION_FACTORY_APP_KEY)
