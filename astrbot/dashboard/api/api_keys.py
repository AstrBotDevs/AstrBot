from fastapi import APIRouter, Depends, Request

from astrbot.core.auth.models import AuthContext as CoreAuthContext
from astrbot.core.auth.models import Resource
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import ApiKeyCreateRequest
from astrbot.dashboard.services.api_key_service import (
    ApiKeyService,
    ApiKeyServiceError,
)

from .auth import AuthContext, require_dashboard_session_principal

router = APIRouter(tags=["API Keys"])


async def require_api_key_access(request: Request, *, action: str) -> AuthContext:
    """Require a Dashboard account for API-key read or write access."""

    principal = await require_dashboard_session_principal(request)
    if principal.account_subject is None:
        raise ApiError("Unauthorized", status_code=401)
    subject = principal.account_subject
    context = CoreAuthContext(
        subject=subject,
        source="dashboard",
        authenticated=True,
        auth_strength=principal.auth_strength,
        authenticated_at=principal.issued_at,
        principal_subject_id=subject.id,
        step_up_token=request.headers.get("X-AstrBot-Step-Up"),
        metadata={"dashboard_session_id": principal.sid},
    )
    runtime = getattr(request.app.state, "runtime", None)
    services = getattr(runtime, "services", None)
    authorization = getattr(services, "authorization", None)
    if authorization is None:
        raise ApiError("Authorization unavailable", status_code=503)
    decision = await authorization.authorize(
        subject,
        action,
        Resource.named("api-key", "collection"),
        context,
    )
    if not decision.allowed:
        raise ApiError("Authorization denied", status_code=403)
    return AuthContext(
        username=principal.username,
        scopes=["*"],
        subject=subject.id,
        account_id=principal.account_id,
        sid=principal.sid,
        auth_strength=principal.auth_strength,
        issued_at=principal.issued_at,
        via="jwt",
    )


async def require_api_key_read(request: Request) -> AuthContext:
    return await require_api_key_access(request, action="identity.read")


async def require_api_key_write(request: Request) -> AuthContext:
    return await require_api_key_access(request, action="identity.manage")


def get_service(request: Request) -> ApiKeyService:
    return request.app.state.services.api_keys


def _payload_dict(payload: ApiKeyCreateRequest) -> dict:
    return payload.model_dump(exclude_none=True)


def _raise_api_key_error(exc: ApiKeyServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _list_api_keys(service: ApiKeyService):
    try:
        return ok(await service.list_api_keys())
    except ApiKeyServiceError as exc:
        _raise_api_key_error(exc)


async def _create_api_key(
    payload: ApiKeyCreateRequest,
    *,
    created_by: str,
    service: ApiKeyService,
):
    try:
        return ok(
            await service.create_api_key(
                _payload_dict(payload),
                created_by=created_by,
            )
        )
    except ApiKeyServiceError as exc:
        _raise_api_key_error(exc)


async def _revoke_api_key(key_id: str, service: ApiKeyService):
    try:
        if not await service.revoke_api_key(key_id):
            raise ApiKeyServiceError("API key not found")
        return ok()
    except ApiKeyServiceError as exc:
        _raise_api_key_error(exc)


async def _delete_api_key(key_id: str, service: ApiKeyService):
    try:
        if not await service.delete_api_key(key_id):
            raise ApiKeyServiceError("API key not found")
        return ok()
    except ApiKeyServiceError as exc:
        _raise_api_key_error(exc)


@router.get("/api-keys")
async def list_api_keys(
    _auth: AuthContext = Depends(require_api_key_read),
    service: ApiKeyService = Depends(get_service),
):
    return await _list_api_keys(service)


@router.post("/api-keys")
async def create_api_key(
    payload: ApiKeyCreateRequest,
    auth: AuthContext = Depends(require_api_key_write),
    service: ApiKeyService = Depends(get_service),
):
    return await _create_api_key(payload, created_by=auth.username, service=service)


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    _auth: AuthContext = Depends(require_api_key_write),
    service: ApiKeyService = Depends(get_service),
):
    return await _revoke_api_key(key_id, service)


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    _auth: AuthContext = Depends(require_api_key_write),
    service: ApiKeyService = Depends(get_service),
):
    return await _delete_api_key(key_id, service)
