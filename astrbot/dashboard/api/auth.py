from dataclasses import dataclass
from urllib.parse import urlsplit

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
from astrbot.dashboard.services.api_key_scopes import (
    DASHBOARD_API_KEY_SCOPES,
    api_key_has_scope,
    effective_api_key_scopes,
)
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import (
    DASHBOARD_JWT_COOKIE_MAX_AGE,
    DASHBOARD_JWT_COOKIE_NAME,
    TOTP_TRUSTED_DEVICE_COOKIE_NAME,
    TOTP_TRUSTED_DEVICE_MAX_AGE,
    AuthService,
    AuthServiceResult,
    DashboardSessionPrincipal,
    DashboardTokenValidator,
)

router = APIRouter(tags=["Auth"])
_SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass(frozen=True)
class AuthContext:
    username: str
    scopes: list[str]
    subject: str
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


def _extract_dashboard_jwt_with_source(
    request: Request,
) -> tuple[str | None, str | None]:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            return token, "bearer"

    cookie_token = request.cookies.get(DASHBOARD_JWT_COOKIE_NAME, "").strip()
    if cookie_token:
        return cookie_token, "cookie"
    return None, None


def _extract_dashboard_jwt(request: Request) -> str | None:
    return _extract_dashboard_jwt_with_source(request)[0]


def _dashboard_token_validator(request: Request) -> DashboardTokenValidator:
    return request.app.state.dashboard_token_validator


def _dashboard_config(request: Request) -> dict:
    config = getattr(request.app.state, "astrbot_config", None)
    if config is None:
        return {}
    dashboard_config = config.get("dashboard", {})
    return dashboard_config if isinstance(dashboard_config, dict) else {}


def _normalized_origin(scheme: str, host: str) -> tuple[str, str, int] | None:
    if not scheme or not host or "," in scheme or "," in host:
        return None
    try:
        parsed = urlsplit(f"{scheme.lower()}://{host}")
        port = parsed.port
    except ValueError:
        return None
    normalized_scheme = parsed.scheme.lower()
    if normalized_scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return (
        normalized_scheme,
        parsed.hostname.lower(),
        port or (443 if normalized_scheme == "https" else 80),
    )


def _request_external_origin(request: Request) -> tuple[str, str, int] | None:
    scheme = request.url.scheme
    host = request.headers.get("host", "")
    if _dashboard_config(request).get("trust_proxy_headers", False):
        forwarded_scheme = (
            request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        )
        forwarded_host = (
            request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        )
        if forwarded_scheme:
            scheme = forwarded_scheme
        if forwarded_host:
            host = forwarded_host
    return _normalized_origin(scheme, host)


def request_external_origin(request: Request) -> str | None:
    """Return the trusted external request origin as an ASCII URL."""
    normalized = _request_external_origin(request)
    if normalized is None:
        return None
    scheme, host, port = normalized
    default_port = 443 if scheme == "https" else 80
    host_text = f"[{host}]" if ":" in host else host
    return f"{scheme}://{host_text}" + ("" if port == default_port else f":{port}")


def _origin_header_value(request: Request) -> tuple[str, str, int] | None:
    origin = request.headers.get("origin", "").strip()
    if not origin or origin == "null" or "," in origin:
        return None
    try:
        parsed = urlsplit(origin)
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    scheme = parsed.scheme.lower()
    return (
        scheme,
        parsed.hostname.lower(),
        port or (443 if scheme == "https" else 80),
    )


def _require_cookie_mutation_origin(request: Request) -> None:
    if request.method.upper() in _SAFE_HTTP_METHODS:
        return
    if _origin_header_value(request) != _request_external_origin(request):
        raise ApiError("Invalid request origin", status_code=403)


def _validate_logout_cookie(
    request: Request,
) -> DashboardSessionPrincipal | None:
    token = request.cookies.get(DASHBOARD_JWT_COOKIE_NAME, "").strip()
    if not token:
        return None
    try:
        principal = _dashboard_token_validator(request).validate(token)
    except jwt.InvalidTokenError:
        return None
    _require_cookie_mutation_origin(request)
    return principal


async def require_dashboard_user(request: Request) -> str:
    if username := _get_dashboard_state_username(request):
        return username

    token, source = _extract_dashboard_jwt_with_source(request)
    if not token:
        raise ApiError("未授权", status_code=401)

    try:
        principal = _dashboard_token_validator(request).validate(token)
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("Token 过期", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("Token 无效", status_code=401) from exc
    if source == "cookie":
        _require_cookie_mutation_origin(request)
    return principal.username


async def require_dashboard_session_principal(
    request: Request,
) -> DashboardSessionPrincipal:
    """Require matching Dashboard Bearer and HttpOnly-cookie sessions."""
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        raise ApiError("Unauthorized", status_code=401)
    bearer_token = auth_header.removeprefix("Bearer ").strip()
    cookie_token = request.cookies.get(DASHBOARD_JWT_COOKIE_NAME, "").strip()
    if not bearer_token or not cookie_token:
        raise ApiError("Unauthorized", status_code=401)
    validator = _dashboard_token_validator(request)
    try:
        bearer_principal = validator.validate(bearer_token)
        cookie_principal = validator.validate(cookie_token)
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("Token expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("Invalid token", status_code=401) from exc
    if (
        bearer_principal.sid != cookie_principal.sid
        or bearer_principal.username != cookie_principal.username
    ):
        raise ApiError("Unauthorized", status_code=401)
    _require_cookie_mutation_origin(request)
    return bearer_principal


async def _require_api_key_scope(
    request: Request,
    raw_key: str,
    scope: str,
) -> AuthContext:
    if scope not in DASHBOARD_API_KEY_SCOPES:
        raise ApiError("Insufficient API key scope", status_code=403)

    key_hash = ApiKeyService.hash_key(raw_key)
    api_key = await request.app.state.db.get_active_api_key_by_hash(key_hash)
    if not api_key:
        raise ApiError("Invalid API key", status_code=401)
    scopes = effective_api_key_scopes(api_key.scopes)
    if not api_key_has_scope(scopes, scope):
        raise ApiError("Insufficient API key scope", status_code=403)
    await request.app.state.db.touch_api_key(api_key.key_id)
    return AuthContext(
        username=f"api_key:{api_key.key_id}",
        scopes=scopes,
        subject=f"api-key:{api_key.key_id}",
        api_key_id=api_key.key_id,
        via="api_key",
    )


async def require_scope(request: Request, scope: str) -> AuthContext:
    raw_key = _extract_raw_api_key(request)
    if raw_key:
        return await _require_api_key_scope(request, raw_key, scope)

    token, source = _extract_dashboard_jwt_with_source(request)
    if not token:
        raise ApiError("Missing API key", status_code=401)
    try:
        principal = _dashboard_token_validator(request).validate(token)
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

    if source == "cookie":
        _require_cookie_mutation_origin(request)
    return AuthContext(
        username=principal.username,
        scopes=["*"],
        subject=f"dashboard-session:{principal.sid}",
        via="jwt",
    )


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


def use_secure_dashboard_cookie(request: Request) -> bool:
    dashboard_config = getattr(request.app.state, "dashboard_config", {})
    default_secure = not bool(getattr(request.app.state, "debug", False)) and not bool(
        getattr(request.app.state, "dashboard_testing", False)
    )
    return bool(
        dashboard_config.get(
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
        secure=use_secure_dashboard_cookie(request),
        path="/api/v1",
    )


def _clear_dashboard_jwt_cookie(request: Request, response: JSONResponse) -> None:
    for path in ("/api/v1", "/"):
        response.delete_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            httponly=True,
            samesite="strict",
            secure=use_secure_dashboard_cookie(request),
            path=path,
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
        secure=use_secure_dashboard_cookie(request),
        path="/api/v1/auth",
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
        response.delete_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            httponly=True,
            samesite="strict",
            secure=use_secure_dashboard_cookie(request),
            path="/",
        )
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
    auth: AuthContext,
    service: AuthService,
):
    return _auth_service_response(
        request,
        await service.totp_setup(_payload(payload), subject=auth.subject),
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


@router.post("/auth/logout")
async def logout(request: Request):
    principal = _validate_logout_cookie(request)
    if principal is not None:
        services = request.app.state.services
        await services.plugin_page_sessions.revoke_by_auth_session_id(principal.sid)
        await services.plugin_file_tickets.revoke_by_auth_session_id(principal.sid)
        await services.auth.discard_totp_rotation(
            f"dashboard-session:{principal.sid}",
        )
    response = JSONResponse(
        {"status": "ok", "message": "已退出登录", "data": {}},
        status_code=200,
    )
    _clear_dashboard_jwt_cookie(request, response)
    return response


@router.get("/auth/setup-status")
async def setup_status(
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


@router.post("/auth/totp/setup")
async def totp_setup(
    request: Request,
    payload: TotpSetupRequest | None = None,
    auth: AuthContext = Depends(require_system_scope),
    service: AuthService = Depends(get_auth_service),
):
    return await _totp_setup(request, payload, auth, service)


@router.post("/auth/totp/recovery")
async def totp_recovery(
    request: Request,
    _auth: AuthContext = Depends(require_system_scope),
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
