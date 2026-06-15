from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import ApiKeyCreateRequest, ApiKeyIdRequest
from astrbot.dashboard.services.api_key_service import (
    ApiKeyService,
    ApiKeyServiceError,
)

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["API Keys"])
legacy_router = APIRouter(
    prefix="/api/apikey",
    tags=["Dashboard API Keys"],
    include_in_schema=False,
)


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")


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
    _auth: AuthContext = Depends(require_system_scope),
    service: ApiKeyService = Depends(get_service),
):
    return await _list_api_keys(service)


@router.post("/api-keys")
async def create_api_key(
    payload: ApiKeyCreateRequest,
    auth: AuthContext = Depends(require_system_scope),
    service: ApiKeyService = Depends(get_service),
):
    return await _create_api_key(payload, created_by=auth.username, service=service)


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    _auth: AuthContext = Depends(require_system_scope),
    service: ApiKeyService = Depends(get_service),
):
    return await _revoke_api_key(key_id, service)


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    _auth: AuthContext = Depends(require_system_scope),
    service: ApiKeyService = Depends(get_service),
):
    return await _delete_api_key(key_id, service)


@legacy_router.get("/list")
async def list_dashboard_api_keys(
    _username: str = Depends(require_dashboard_user),
    service: ApiKeyService = Depends(get_service),
):
    return await _list_api_keys(service)


@legacy_router.post("/create")
async def create_dashboard_api_key(
    payload: ApiKeyCreateRequest,
    username: str = Depends(require_dashboard_user),
    service: ApiKeyService = Depends(get_service),
):
    return await _create_api_key(payload, created_by=username, service=service)


@legacy_router.post("/revoke")
async def revoke_dashboard_api_key(
    payload: ApiKeyIdRequest,
    _username: str = Depends(require_dashboard_user),
    service: ApiKeyService = Depends(get_service),
):
    return await _revoke_api_key(payload.key_id, service)


@legacy_router.post("/delete")
async def delete_dashboard_api_key(
    payload: ApiKeyIdRequest,
    _username: str = Depends(require_dashboard_user),
    service: ApiKeyService = Depends(get_service),
):
    return await _delete_api_key(payload.key_id, service)
