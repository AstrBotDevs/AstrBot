"""Dashboard-session-only runtime data file manager API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import StreamingResponse

from astrbot.core.auth.models import AuthContext, Resource, Role, Subject
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    DataFileContentRequest,
    DataFileDeleteRequest,
    DataFileEntryRequest,
    DataFileMoveRequest,
)
from astrbot.dashboard.services.auth_service import DashboardSessionPrincipal
from astrbot.dashboard.services.data_file_service import (
    DATA_UPLOAD_REQUEST_MAX_BYTES,
    DataFileService,
    DataFileServiceError,
)
from astrbot.dashboard.services.plugin_file_ticket_service import (
    content_disposition_header,
)

from .auth import object_resource, require_dashboard_session_principal

router = APIRouter(tags=["Data Files"])
_BINARY_FILE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Raw runtime data file download",
        "content": {
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            }
        },
    }
}


def get_service(request: Request) -> DataFileService:
    return request.app.state.services.data_files


def _context(
    principal: DashboardSessionPrincipal, request: Request
) -> tuple[Subject, AuthContext]:
    subject = principal.account_subject
    if subject is None:
        raise ApiError("Dashboard account is unavailable", status_code=401)
    return subject, AuthContext(
        subject=subject,
        source="dashboard",
        authenticated=True,
        principal_subject_id=subject.id,
        auth_strength=principal.auth_strength,
        authenticated_at=principal.issued_at,
        step_up_token=request.headers.get("X-AstrBot-Step-Up"),
        metadata={"dashboard_session_id": principal.sid},
    )


async def _authorize(
    request: Request,
    principal: DashboardSessionPrincipal,
    *,
    action: str,
    resource: Resource,
) -> Any:
    subject, context = _context(principal, request)
    authorization = getattr(request.app.state.runtime.services, "authorization", None)
    if authorization is None:
        raise ApiError("Authorization unavailable", status_code=503)
    decision = await authorization.authorize(subject, action, resource, context)
    if not decision.allowed:
        raise ApiError(
            "Authorization denied",
            data={"requires_step_up": decision.requires_step_up},
            status_code=403,
        )
    return decision


def _rights(decision: Any) -> dict[str, bool]:
    role = getattr(decision, "effective_role", None)
    is_root = role == Role.ROOT
    action = str(getattr(decision, "action", ""))
    return {
        "can_read": action == "filesystem.read",
        "can_write": action in {"filesystem.write", "filesystem.manage"}
        or (action == "filesystem.read" and role in {Role.OPERATOR, Role.ROOT}),
        "can_manage": action == "filesystem.manage",
        "is_root": is_root,
    }


async def _authorize_path(
    request: Request,
    principal: DashboardSessionPrincipal,
    service: DataFileService,
    path: str,
    *,
    mutation: bool,
) -> tuple[Any, dict[str, bool], str]:
    normalized = service.normalize_relative_path(path, allow_empty=not mutation)
    if mutation:
        metadata = service.metadata(
            normalized, can_read=True, can_write=False, can_manage=False, is_root=False
        )
        action = (
            "filesystem.manage" if metadata.get("protected") else "filesystem.write"
        )
    else:
        action = "filesystem.read"
    resource = (
        Resource.named("filesystem", "collection")
        if not normalized
        else object_resource("filesystem", normalized)
    )
    decision = await _authorize(request, principal, action=action, resource=resource)
    rights = _rights(decision)
    return decision, rights, normalized


def _raise(exc: DataFileServiceError) -> None:
    raise ApiError(str(exc), status_code=exc.status_code) from exc


def _record_mutation(
    request: Request,
    principal: DashboardSessionPrincipal,
    decision: Any,
    relative_path: str,
    *,
    category: str | None = None,
    size: int | None = None,
) -> None:
    authorization = getattr(request.app.state.runtime.services, "authorization", None)
    record = getattr(authorization, "record_dashboard_operation", None)
    if not callable(record):
        return
    subject, context = _context(principal, request)
    metadata = {"category": category, "size": size}
    record(
        subject=subject,
        action=decision.action,
        resource=object_resource("filesystem", relative_path),
        context=context,
        effective_role=decision.effective_role,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


@router.get("/data-files/tree")
async def tree(
    request: Request,
    path: str = "",
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        _decision, rights, normalized = await _authorize_path(
            request, principal, service, path, mutation=False
        )
        return ok(service.tree(normalized, **rights))
    except DataFileServiceError as exc:
        _raise(exc)


@router.get("/data-files/metadata")
async def metadata(
    request: Request,
    path: str = "",
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        _decision, rights, normalized = await _authorize_path(
            request, principal, service, path, mutation=False
        )
        return ok(service.metadata(normalized, **rights))
    except DataFileServiceError as exc:
        _raise(exc)


@router.get("/data-files/content/{path:path}")
async def content(
    path: str,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        decision, rights, normalized = await _authorize_path(
            request, principal, service, path, mutation=False
        )
        try:
            return ok(service.read_text(normalized, **rights))
        except DataFileServiceError as exc:
            _raise(exc)
    except DataFileServiceError as exc:
        _raise(exc)


@router.put("/data-files/content/{path:path}")
async def update_content(
    path: str,
    payload: DataFileContentRequest,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        _decision, rights, normalized = await _authorize_path(
            request, principal, service, path, mutation=True
        )
        expected = payload.expected_etag or if_match
        if expected is None:
            raise DataFileServiceError("An expected ETag is required", status_code=428)
        managed = service.is_managed_config_path(normalized)
        if managed:
            result = await service.write_managed_text(
                normalized, payload.content, expected_etag=expected, **rights
            )
        else:
            result = service.write_text(
                normalized, payload.content, expected_etag=expected, **rights
            )
        _record_mutation(
            request,
            principal,
            _decision,
            normalized,
            category="text",
            size=result["size"],
        )
        return ok(result)
    except DataFileServiceError as exc:
        _raise(exc)


@router.post("/data-files/entries")
async def create_entry(
    payload: DataFileEntryRequest,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        normalized = service.normalize_relative_path(payload.path, allow_empty=False)
        parent = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
        action = (
            "filesystem.manage"
            if service.path_is_protected(normalized)
            else "filesystem.write"
        )
        decision = await _authorize(
            request,
            principal,
            action=action,
            resource=Resource.named("filesystem", "collection")
            if not parent
            else object_resource("filesystem", parent),
        )
        rights = _rights(decision)
        # Creation authorizes the parent and reclassifies the new target in the service.
        result = service.create(
            normalized, payload.type, content=payload.content, **rights
        )
        _record_mutation(
            request,
            principal,
            decision,
            normalized,
            category=result["category"],
            size=result["size"],
        )
        return ok(result)
    except DataFileServiceError as exc:
        _raise(exc)


@router.patch("/data-files/entries")
async def move_entry(
    payload: DataFileMoveRequest,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        source = service.normalize_relative_path(payload.source_path, allow_empty=False)
        target = service.normalize_relative_path(payload.target_path, allow_empty=False)
        source_protected = service.metadata(
            source, can_read=True, can_write=False, can_manage=False, is_root=False
        ).get("protected", False)
        action = (
            "filesystem.manage"
            if source_protected or service.path_is_protected(target)
            else "filesystem.write"
        )
        decision = await _authorize(
            request,
            principal,
            action=action,
            resource=object_resource("filesystem", source),
        )
        rights = _rights(decision)
        result = service.move(payload.source_path, payload.target_path, **rights)
        _record_mutation(
            request,
            principal,
            decision,
            result["path"],
            category=result["category"],
            size=result["size"],
        )
        return ok(result)
    except DataFileServiceError as exc:
        _raise(exc)


@router.delete("/data-files/entries/{path:path}")
async def delete_entry(
    path: str,
    request: Request,
    payload: DataFileDeleteRequest | None = None,
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        decision, rights, normalized = await _authorize_path(
            request, principal, service, path, mutation=True
        )
        recursive = (
            bool(payload.recursive)
            if payload
            else request.query_params.get("recursive") == "true"
        )
        service.delete(normalized, recursive=recursive, **rights)
        _record_mutation(request, principal, decision, normalized)
        return ok()
    except DataFileServiceError as exc:
        _raise(exc)


@router.post("/data-files/upload")
async def upload(
    request: Request,
    path: str = Form(...),
    file: UploadFile = File(...),
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        length = request.headers.get("content-length")
        if length and int(length) > DATA_UPLOAD_REQUEST_MAX_BYTES:
            raise ApiError("Upload request is too large", status_code=413)
        normalized = service.normalize_relative_path(path, allow_empty=False)
        parent = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
        decision = await _authorize(
            request,
            principal,
            action=(
                "filesystem.manage"
                if service.path_is_protected(normalized)
                else "filesystem.write"
            ),
            resource=(
                Resource.named("filesystem", "collection")
                if not parent
                else object_resource("filesystem", parent)
            ),
        )
        rights = _rights(decision)
        result = await service.upload(normalized, file, **rights)
        _record_mutation(
            request,
            principal,
            decision,
            normalized,
            category=result["category"],
            size=result["size"],
        )
        return ok(result)
    except ValueError as exc:
        raise ApiError("Invalid Content-Length", status_code=422) from exc
    except DataFileServiceError as exc:
        _raise(exc)


@router.get("/data-files/search")
async def search(
    request: Request,
    q: str,
    path: str = "",
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        _decision, rights, normalized = await _authorize_path(
            request, principal, service, path, mutation=False
        )
        return ok(
            await service.search(
                q, normalized, is_root=rights["is_root"], can_read=rights["can_read"]
            )
        )
    except DataFileServiceError as exc:
        _raise(exc)


@router.get("/data-files/download/{path:path}", responses=_BINARY_FILE_RESPONSE)
async def download(
    path: str,
    request: Request,
    principal: DashboardSessionPrincipal = Depends(require_dashboard_session_principal),
    service: DataFileService = Depends(get_service),
):
    try:
        normalized = service.normalize_relative_path(path, allow_empty=False)
        sensitive = service.path_is_sensitive(normalized)
        action = "filesystem.manage" if sensitive else "filesystem.read"
        decision = await _authorize(
            request,
            principal,
            action=action,
            resource=object_resource("filesystem", normalized),
        )
        rights = _rights(decision)
        if sensitive:
            if not rights["is_root"]:
                raise ApiError("Authorization denied", status_code=403)
            rights["can_read"] = True
        opened = service.open_download(
            normalized,
            is_root=rights["is_root"],
            can_read=rights["can_read"],
            can_manage=rights["can_manage"],
        )
    except DataFileServiceError as exc:
        _raise(exc)

    def iterator():
        with os.fdopen(opened.fd, "rb", closefd=True) as handle:
            while chunk := handle.read(1024 * 1024):
                yield chunk

    headers = {
        "Content-Disposition": content_disposition_header(
            "attachment", opened.entry["name"]
        ),
        "Content-Length": str(opened.entry["size"]),
        "Cache-Control": "no-store",
    }
    return StreamingResponse(
        iterator(), media_type=opened.content_type, headers=headers
    )
