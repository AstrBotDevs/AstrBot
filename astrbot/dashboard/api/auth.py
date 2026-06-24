from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.schemas import (
    AccountUpdateRequest,
    AuthSetupRequest,
    LoginRequest,
    TotpSetupRequest,
)
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import (
    ALL_OPEN_API_SCOPES,
    DASHBOARD_JWT_COOKIE_MAX_AGE,
    DASHBOARD_JWT_COOKIE_NAME,
    OPEN_API_SCOPE_INCLUDES,
    TOTP_TRUSTED_DEVICE_COOKIE_NAME,
    TOTP_TRUSTED_DEVICE_MAX_AGE,
    AuthService,
    AuthServiceResult,
)

router = APIRouter(tags=["Auth"])
legacy_router = APIRouter(
    prefix="/api/auth",
    tags=["Dashboard Auth"],
    include_in_schema=False,
)


@dataclass(frozen=True)
class AuthContext:
    username: str
    scopes: list[str]
    api_key_id: str | None = None
    via: str = "jwt"


def _extract_raw_api_key(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return None
    if auth_header.startswith("ApiKey "):
        return auth_header.removeprefix("ApiKey ").strip()
    if key := request.query_params.get("api_key"):
        return key.strip()
    if key := request.query_params.get("key"):
        return key.strip()
    if key := request.headers.get("X-API-Key"):
        return key.strip()
    return None


def _get_dashboard_state_username(request: Request) -> str | None:
    dashboard_g = getattr(request.state, "dashboard_g", None)
    if dashboard_g is None:
        return None

    username = getattr(dashboard_g, "username", None)
    if username is None and hasattr(dashboard_g, "get"):
        username = dashboard_g.get("username")
    if isinstance(username, str) and username.strip():
        return username
    return None


def _extract_dashboard_jwt(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            return token

    cookie_token = request.cookies.get(DASHBOARD_JWT_COOKIE_NAME, "").strip()
    if cookie_token:
        return cookie_token
    return None


async def require_dashboard_user(request: Request) -> str:
    if username := _get_dashboard_state_username(request):
        return username

    token = _extract_dashboard_jwt(request)
    if not token:
        raise ApiError("未授权", status_code=401)

    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("Token 过期", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("Token 无效", status_code=401) from exc

    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ApiError("Token 无效", status_code=401)
    return username


async def _require_api_key_scope(
    request: Request,
    raw_key: str,
    scope: str,
) -> AuthContext:
    if scope not in ALL_OPEN_API_SCOPES:
        raise ApiError("Insufficient API key scope", status_code=403)

    key_hash = ApiKeyService.hash_key(raw_key)
    api_key = await request.app.state.db.get_active_api_key_by_hash(key_hash)
    if not api_key:
        raise ApiError("Invalid API key", status_code=401)
    scopes = (
        [str(scope) for scope in api_key.scopes]
        if isinstance(api_key.scopes, list)
        else [str(scope) for scope in ALL_OPEN_API_SCOPES]
    )
    if (
        "*" not in scopes
        and scope not in scopes
        and not any(
            scope in OPEN_API_SCOPE_INCLUDES.get(api_key_scope, ())
            for api_key_scope in scopes
        )
    ):
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

    token = _extract_dashboard_jwt(request)
    if not token:
        raise ApiError("Missing API key", status_code=401)
    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("Token expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            try:
                return await _require_api_key_scope(request, token, scope)
            except ApiError as api_key_exc:
                raise api_key_exc from exc
        raise ApiError("Invalid token", status_code=401) from exc

    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ApiError("Invalid token", status_code=401)
    return AuthContext(username=username, scopes=["*"], via="jwt")


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.services.auth


def _payload(payload) -> dict:
    if payload is None:
        return {}
    return payload.model_dump(exclude_none=True)


def _auth_result_payload(result: AuthServiceResult) -> dict:
    data = result.data if result.data is not None else {}
    payload = {
        "status": result.status,
        "message": result.message,
        "data": data,
    }
    if result.status == "error" and result.data is None:
        payload["data"] = None
    return payload


def _use_secure_dashboard_jwt_cookie(request: Request) -> bool:
    adapter = getattr(request.app.state, "dashboard_app_adapter", None)
    adapter_config = getattr(adapter, "config", {}) if adapter is not None else {}
    default_secure = not bool(getattr(adapter, "debug", False)) and not bool(
        getattr(adapter, "testing", False)
    )
    return bool(
        adapter_config.get(
            "DASHBOARD_JWT_COOKIE_SECURE",
            default_secure,
        )
    )


def _set_dashboard_jwt_cookie(
    request: Request,
    response: JSONResponse,
    token: str,
) -> None:
    response.set_cookie(
        DASHBOARD_JWT_COOKIE_NAME,
        token,
        max_age=DASHBOARD_JWT_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=_use_secure_dashboard_jwt_cookie(request),
        path="/",
    )


def _clear_dashboard_jwt_cookie(request: Request, response: JSONResponse) -> None:
    response.delete_cookie(
        DASHBOARD_JWT_COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=_use_secure_dashboard_jwt_cookie(request),
        path="/",
    )


def _set_trusted_device_cookie(
    request: Request,
    response: JSONResponse,
    token: str,
) -> None:
    response.set_cookie(
        TOTP_TRUSTED_DEVICE_COOKIE_NAME,
        token,
        max_age=TOTP_TRUSTED_DEVICE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=_use_secure_dashboard_jwt_cookie(request),
        path="/api/auth",
    )


def _auth_service_response(
    request: Request,
    result: AuthServiceResult,
) -> JSONResponse:
    response = JSONResponse(
        _auth_result_payload(result),
        status_code=result.status_code,
    )
    if result.jwt_token:
        _set_dashboard_jwt_cookie(request, response, result.jwt_token)
    if result.trusted_device_token:
        _set_trusted_device_cookie(request, response, result.trusted_device_token)
    return response


def _has_auth_credentials(request: Request) -> bool:
    auth_header = request.headers.get("Authorization", "")
    return bool(
        auth_header.startswith(("Bearer ", "ApiKey "))
        or request.query_params.get("api_key")
        or request.query_params.get("key")
        or request.headers.get("X-API-Key")
    )


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")


async def optional_system_auth(request: Request) -> AuthContext | None:
    if not _has_auth_credentials(request):
        return None
    return await require_system_scope(request)


async def _login(
    request: Request,
    payload: LoginRequest,
    service: AuthService,
):
    result = await service.login(
        _payload(payload),
        trusted_device_cookie_token=request.cookies.get(
            TOTP_TRUSTED_DEVICE_COOKIE_NAME,
            "",
        ).strip(),
    )
    return _auth_service_response(
        request,
        result,
    )


async def _setup_status(service: AuthService):
    return _auth_service_response_from_result(await service.setup_status())


def _auth_service_response_from_result(result: AuthServiceResult) -> JSONResponse:
    return JSONResponse(
        _auth_result_payload(result),
        status_code=result.status_code,
    )


async def _setup(
    request: Request,
    payload: AuthSetupRequest,
    service: AuthService,
    auth: AuthContext | None,
):
    if auth is None:
        result = await service.setup(_payload(payload))
    else:
        result = await service.setup_authenticated(_payload(payload), auth.username)
    return _auth_service_response(
        request,
        result,
    )


async def _totp_setup(
    request: Request,
    payload: TotpSetupRequest | None,
    service: AuthService,
):
    return _auth_service_response(
        request,
        await service.totp_setup(_payload(payload)),
    )


async def _totp_recovery(
    request: Request,
    service: AuthService,
):
    return _auth_service_response(request, await service.totp_recovery())


async def _update_account(
    request: Request,
    payload: AccountUpdateRequest,
    service: AuthService,
):
    return _auth_service_response(
        request,
        await service.edit_account(_payload(payload)),
    )


@router.post("/auth/login")
async def login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await _login(request, payload, service)


@legacy_router.post("/login")
async def dashboard_login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await _login(request, payload, service)


@router.post("/auth/logout")
async def logout(request: Request):
    response = JSONResponse(
        {"status": "ok", "message": "已退出登录", "data": {}},
        status_code=200,
    )
    _clear_dashboard_jwt_cookie(request, response)
    return response


@legacy_router.post("/logout")
async def dashboard_logout(request: Request):
    return await logout(request)


@router.get("/auth/setup-status")
async def setup_status(
    service: AuthService = Depends(get_auth_service),
):
    return _auth_service_response_from_result(await service.setup_status())


@legacy_router.get("/setup-status")
async def dashboard_setup_status(
    service: AuthService = Depends(get_auth_service),
):
    return _auth_service_response_from_result(await service.setup_status())


@router.post("/auth/setup")
async def setup(
    request: Request,
    payload: AuthSetupRequest,
    auth: AuthContext | None = Depends(optional_system_auth),
    service: AuthService = Depends(get_auth_service),
):
    return await _setup(request, payload, service, auth)


@legacy_router.post("/setup")
async def dashboard_setup(
    request: Request,
    payload: AuthSetupRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await _setup(request, payload, service, None)


@legacy_router.post("/setup-authenticated")
async def dashboard_setup_authenticated(
    request: Request,
    payload: AuthSetupRequest,
    username: str = Depends(require_dashboard_user),
    service: AuthService = Depends(get_auth_service),
):
    auth = AuthContext(username=username, scopes=["*"], via="jwt")
    return await _setup(request, payload, service, auth)


@router.post("/auth/totp/setup")
async def totp_setup(
    request: Request,
    payload: TotpSetupRequest | None = None,
    _auth: AuthContext = Depends(require_system_scope),
    service: AuthService = Depends(get_auth_service),
):
    return await _totp_setup(request, payload, service)


@legacy_router.post("/totp/setup")
async def dashboard_totp_setup(
    request: Request,
    payload: TotpSetupRequest | None = None,
    _username: str = Depends(require_dashboard_user),
    service: AuthService = Depends(get_auth_service),
):
    return await _totp_setup(request, payload, service)


@router.post("/auth/totp/recovery")
async def totp_recovery(
    request: Request,
    _auth: AuthContext = Depends(require_system_scope),
    service: AuthService = Depends(get_auth_service),
):
    return await _totp_recovery(request, service)


@legacy_router.post("/totp/recovery")
async def dashboard_totp_recovery(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: AuthService = Depends(get_auth_service),
):
    return await _totp_recovery(request, service)


@router.patch("/auth/account")
async def update_account(
    request: Request,
    payload: AccountUpdateRequest,
    _auth: AuthContext = Depends(require_system_scope),
    service: AuthService = Depends(get_auth_service),
):
    return await _update_account(request, payload, service)


@legacy_router.post("/account/edit")
async def dashboard_update_account(
    request: Request,
    payload: AccountUpdateRequest,
    _username: str = Depends(require_dashboard_user),
    service: AuthService = Depends(get_auth_service),
):
    return await _update_account(request, payload, service)
