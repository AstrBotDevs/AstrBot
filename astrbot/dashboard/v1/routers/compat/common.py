from __future__ import annotations

from fastapi import Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext, require_scope


def get_bridge(request: Request) -> DashboardRouteBridgeService:
    return request.app.state.services.route_bridge


async def json_or_empty(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


async def auth_optional(request: Request) -> AuthContext | None:
    auth_header = request.headers.get("Authorization", "")
    has_api_key = bool(
        request.query_params.get("api_key")
        or request.query_params.get("key")
        or request.headers.get("X-API-Key")
    )
    if auth_header.startswith(("Bearer ", "ApiKey ")) or has_api_key:
        return await require_scope(request, "system")
    return None


async def require_chat_scope(request: Request) -> AuthContext:
    return await require_scope(request, "chat")


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


async def require_data_scope(request: Request) -> AuthContext:
    return await require_scope(request, "data")


async def require_file_scope(request: Request) -> AuthContext:
    return await require_scope(request, "file")


async def require_kb_scope(request: Request) -> AuthContext:
    return await require_scope(request, "kb")


async def require_persona_scope(request: Request) -> AuthContext:
    return await require_scope(request, "persona")


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")
