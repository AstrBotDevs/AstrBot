"""Dashboard Extension Protocol v1 control-plane routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from astrbot.dashboard.responses import ApiError, error, ok
from astrbot.dashboard.schemas import (
    PluginDashboardActionRequest,
    PluginDashboardFileRequest,
    PluginDashboardSessionRequest,
    PluginDashboardUploadMetadata,
)
from astrbot.dashboard.services.auth_service import DashboardSessionPrincipal
from astrbot.dashboard.services.plugin_dashboard_service import (
    MAX_JSON_REQUEST_BYTES,
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_METADATA_BYTES,
    PluginDashboardRateLimitError,
    PluginDashboardService,
)
from astrbot.dashboard.services.static_file_service import StaticFileService

from .auth import (
    AuthContext,
    require_dashboard_control_plane_principal,
    require_scope,
    use_secure_dashboard_cookie,
)

router = APIRouter(tags=["Plugin Dashboard"])
_DASHBOARD_SESSION_SECURITY = [{"DashboardBearerAuth": [], "DashboardCookieAuth": []}]
_UPLOAD_OPENAPI_EXTRA = {
    "security": _DASHBOARD_SESSION_SECURITY,
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["metadata", "file"],
                    "properties": {
                        "metadata": {
                            "type": "string",
                            "description": "PluginDashboardUploadMetadata JSON",
                        },
                        "file": {"type": "string", "format": "binary"},
                    },
                    "additionalProperties": False,
                },
                "encoding": {"metadata": {"contentType": "application/json"}},
            }
        },
    },
}
_SET_COOKIE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Success with an exact-Path HttpOnly capability cookie",
        "headers": {"Set-Cookie": {"schema": {"type": "string"}}},
    }
}
_STATIC_FILE_SERVICE = StaticFileService()


def get_service(request: Request) -> PluginDashboardService:
    return request.app.state.services.plugin_dashboard


async def require_plugin_dashboard_read_scope(request: Request) -> AuthContext:
    """Authorize Dashboard Extension catalog and page-session access."""

    return await require_scope(
        request,
        "plugin",
        action_override="extension.read",
    )


async def require_plugin_dashboard_action_scope(
    request: Request,
    service: PluginDashboardService,
    extension_id: str,
    action_id: str,
) -> AuthContext:
    """Authorize an extension Action by its declared stable API scope."""

    return await require_scope(
        request,
        service.action_required_scope(extension_id, action_id),
    )


def require_plugin_ui_protocol(request: Request) -> None:
    static_folder = getattr(request.app.state, "dashboard_static_folder", None)
    if static_folder is None:
        return
    if not _STATIC_FILE_SERVICE.is_plugin_ui_protocol_compatible(static_folder):
        raise ApiError(
            "Dashboard Plugin UI protocol mismatch; rebuild or replace the Dashboard",
            status_code=503,
        )


def _rate_limit_response(exc: PluginDashboardRateLimitError) -> JSONResponse:
    return JSONResponse(
        error(exc.message),
        status_code=429,
        headers={"Retry-After": str(exc.retry_after)},
    )


def _require_json_content_length(request: Request) -> None:
    raw_length = request.headers.get("content-length")
    if not raw_length:
        return
    try:
        if int(raw_length) > MAX_JSON_REQUEST_BYTES:
            raise ApiError("Request body is too large", status_code=413)
    except ValueError as exc:
        raise ApiError("Invalid Content-Length", status_code=422) from exc


@router.get(
    "/plugins/{extension_id}/dashboard",
    openapi_extra={"security": _DASHBOARD_SESSION_SECURITY},
)
async def get_plugin_dashboard_catalog(
    extension_id: str,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(
        require_dashboard_control_plane_principal
    ),
    service: PluginDashboardService = Depends(get_service),
):
    require_plugin_ui_protocol(request)
    await require_plugin_dashboard_read_scope(request)
    return ok(service.catalog(extension_id, principal))


@router.post(
    "/plugins/{extension_id}/dashboard/pages/{page_id}/session",
    openapi_extra={"security": _DASHBOARD_SESSION_SECURITY},
    responses=_SET_COOKIE_RESPONSE,
)
async def create_plugin_page_session(
    extension_id: str,
    page_id: str,
    payload: PluginDashboardSessionRequest,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(
        require_dashboard_control_plane_principal
    ),
    service: PluginDashboardService = Depends(get_service),
):
    require_plugin_ui_protocol(request)
    await require_plugin_dashboard_read_scope(request)
    _require_json_content_length(request)
    try:
        created = await service.create_page_session(
            extension_id,
            page_id,
            payload.expected_generation,
            principal,
        )
    except PluginDashboardRateLimitError as exc:
        return _rate_limit_response(exc)
    response = JSONResponse(ok(created.data))
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        "astrbot_plugin_page",
        created.cookie_secret,
        max_age=created.cookie_max_age,
        httponly=True,
        samesite="strict",
        secure=use_secure_dashboard_cookie(request),
        path=created.cookie_path,
    )
    return response


@router.post(
    "/plugins/{extension_id}/dashboard/actions/{action_id}",
    openapi_extra={"security": _DASHBOARD_SESSION_SECURITY},
)
async def invoke_plugin_dashboard_action(
    extension_id: str,
    action_id: str,
    payload: PluginDashboardActionRequest,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(
        require_dashboard_control_plane_principal
    ),
    service: PluginDashboardService = Depends(get_service),
):
    require_plugin_ui_protocol(request)
    await require_plugin_dashboard_action_scope(
        request,
        service,
        extension_id,
        action_id,
    )
    _require_json_content_length(request)
    try:
        data = await service.invoke_json(
            extension_id,
            action_id,
            payload.instance_id,
            payload.expected_generation,
            payload.payload,
            principal,
        )
    except PluginDashboardRateLimitError as exc:
        return _rate_limit_response(exc)
    return ok(data)


async def _multipart_parts(
    request: Request,
) -> tuple[PluginDashboardUploadMetadata, UploadFile]:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data;"):
        raise ApiError("Content-Type must be multipart/form-data", status_code=415)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if (
                int(content_length)
                > MAX_UPLOAD_FILE_BYTES + MAX_UPLOAD_METADATA_BYTES + 64 * 1024
            ):
                raise ApiError("Upload is too large", status_code=413)
        except ValueError as exc:
            raise ApiError("Invalid Content-Length", status_code=422) from exc
    try:
        form = await request.form(
            max_files=2,
            max_fields=2,
            max_part_size=MAX_UPLOAD_METADATA_BYTES + 1,
        )
    except StarletteHTTPException as exc:
        raise ApiError("Invalid multipart upload", status_code=422) from exc
    parts = form.multi_items()
    if len(parts) != 2 or {name for name, _value in parts} != {"metadata", "file"}:
        for _name, value in parts:
            if isinstance(value, UploadFile):
                await value.close()
        raise ApiError("Upload requires metadata and file", status_code=422)
    metadata_values = [value for name, value in parts if name == "metadata"]
    file_values = [value for name, value in parts if name == "file"]
    if (
        len(metadata_values) != 1
        or len(file_values) != 1
        or not isinstance(metadata_values[0], UploadFile)
        or not isinstance(file_values[0], UploadFile)
    ):
        raise ApiError("Invalid multipart upload", status_code=422)
    metadata_file = metadata_values[0]
    upload = file_values[0]
    header_bytes = sum(
        len(name) + len(value) + 4
        for item in (metadata_file, upload)
        for name, value in Headers(raw=item.headers.raw).items()
    )
    if header_bytes > 16 * 1024:
        await metadata_file.close()
        await upload.close()
        raise ApiError("Multipart headers are too large", status_code=413)
    if (metadata_file.content_type or "").split(";", 1)[
        0
    ].lower() != "application/json":
        await metadata_file.close()
        await upload.close()
        raise ApiError("Metadata must be application/json", status_code=422)
    raw_metadata = await metadata_file.read(MAX_UPLOAD_METADATA_BYTES + 1)
    await metadata_file.close()
    if len(raw_metadata) > MAX_UPLOAD_METADATA_BYTES:
        await upload.close()
        raise ApiError("Upload metadata is too large", status_code=413)
    try:
        metadata = PluginDashboardUploadMetadata.model_validate(
            json.loads(raw_metadata.decode("utf-8"))
        )
    except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        await upload.close()
        raise ApiError("Invalid upload metadata", status_code=422) from exc
    return metadata, upload


@router.post(
    "/plugins/{extension_id}/dashboard/uploads/{action_id}",
    openapi_extra=_UPLOAD_OPENAPI_EXTRA,
)
async def invoke_plugin_dashboard_upload(
    extension_id: str,
    action_id: str,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(
        require_dashboard_control_plane_principal
    ),
    service: PluginDashboardService = Depends(get_service),
):
    require_plugin_ui_protocol(request)
    await require_plugin_dashboard_action_scope(
        request,
        service,
        extension_id,
        action_id,
    )
    metadata, upload = await _multipart_parts(request)
    try:
        data = await service.invoke_upload(
            extension_id,
            action_id,
            metadata.instance_id,
            metadata.expected_generation,
            metadata.fields,
            upload,
            principal,
        )
    except PluginDashboardRateLimitError as exc:
        await upload.close()
        return _rate_limit_response(exc)
    return ok(data)


@router.post(
    "/plugins/{extension_id}/dashboard/files/{action_id}",
    openapi_extra={"security": _DASHBOARD_SESSION_SECURITY},
    responses=_SET_COOKIE_RESPONSE,
)
async def invoke_plugin_dashboard_file(
    extension_id: str,
    action_id: str,
    payload: PluginDashboardFileRequest,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(
        require_dashboard_control_plane_principal
    ),
    service: PluginDashboardService = Depends(get_service),
):
    require_plugin_ui_protocol(request)
    await require_plugin_dashboard_action_scope(
        request,
        service,
        extension_id,
        action_id,
    )
    _require_json_content_length(request)
    try:
        created = await service.invoke_file(
            extension_id,
            action_id,
            payload.instance_id,
            payload.expected_generation,
            payload.expected_disposition,
            payload.payload,
            principal,
        )
    except PluginDashboardRateLimitError as exc:
        return _rate_limit_response(exc)
    response = JSONResponse(ok(created.data))
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        "astrbot_plugin_file",
        created.cookie_secret,
        max_age=created.cookie_max_age,
        httponly=True,
        samesite="strict",
        secure=use_secure_dashboard_cookie(request),
        path=created.cookie_path,
    )
    return response
