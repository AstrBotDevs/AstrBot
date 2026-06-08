from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Request

from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import ALL_OPEN_API_SCOPES

from .responses import ApiError


@dataclass(frozen=True)
class AuthContext:
    username: str
    scopes: list[str]
    api_key_id: str | None = None
    via: str = "jwt"


def _extract_raw_api_key(request: Request) -> str | None:
    if key := request.query_params.get("api_key"):
        return key.strip()
    if key := request.query_params.get("key"):
        return key.strip()
    if key := request.headers.get("X-API-Key"):
        return key.strip()
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("ApiKey "):
        return auth_header.removeprefix("ApiKey ").strip()
    return None


async def _require_api_key_scope(
    request: Request,
    raw_key: str,
    scope: str,
) -> AuthContext:
    key_hash = ApiKeyService.hash_key(raw_key)
    api_key = await request.app.state.db.get_active_api_key_by_hash(key_hash)
    if not api_key:
        raise ApiError("Invalid API key", status_code=401)
    scopes = (
        api_key.scopes
        if isinstance(api_key.scopes, list)
        else list(ALL_OPEN_API_SCOPES)
    )
    if "*" not in scopes and scope not in scopes:
        raise ApiError("Insufficient API key scope", status_code=403)
    await request.app.state.db.touch_api_key(api_key.key_id)
    return AuthContext(
        username=f"api_key:{api_key.key_id}",
        scopes=scopes,
        api_key_id=api_key.key_id,
        via="api_key",
    )


async def require_scope(request: Request, scope: str) -> AuthContext:
    raw_key = _extract_raw_api_key(request)
    if raw_key:
        return await _require_api_key_scope(request, raw_key, scope)

    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        raise ApiError("Missing API key", status_code=401)
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("Token expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        try:
            return await _require_api_key_scope(request, token, scope)
        except ApiError as api_key_exc:
            raise api_key_exc from exc

    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ApiError("Invalid token", status_code=401)
    return AuthContext(username=username, scopes=["*"], via="jwt")
