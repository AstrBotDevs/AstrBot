from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from astrbot.core import logger
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import (
    SkillByNameUpdateRequest,
    SkillFileUpdateRequest,
    SkillNeoRequest,
    SkillUpdateRequest,
)
from astrbot.dashboard.services.skills_service import (
    SkillArchive,
    SkillsOperationResult,
    SkillsService,
    SkillsServiceError,
)

from .auth import AuthContext, require_dashboard_user, require_scope
from .multipart import multipart_parts, single_upload

router = APIRouter(tags=["Skills"])
legacy_router = APIRouter(
    prefix="/api/skills",
    tags=["Dashboard Skills"],
    include_in_schema=False,
)


def get_service(request: Request) -> SkillsService:
    return request.app.state.services.skills


async def require_skill_scope(request: Request) -> AuthContext:
    return await require_scope(request, "skill")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _required_text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing key: {name}")
    return text


def _model_dict(payload) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


def _serialize_result(result: SkillsOperationResult):
    if result.ok:
        return ok(result.data, result.message)
    return error(result.message or "", result.data)


async def _run(operation, *, trace: bool = True):
    try:
        result = await run_maybe_async(operation)
        if isinstance(result, SkillsOperationResult):
            return _serialize_result(result)
        return ok(result)
    except SkillsServiceError as exc:
        return error(str(exc))
    except Exception as exc:
        logger.error(str(exc), exc_info=trace)
        return error(str(exc))


def _archive_response(archive: SkillArchive):
    return FileResponse(
        archive.path,
        filename=archive.filename,
        media_type="application/zip",
    )


async def _download_skill(service: SkillsService, name: str):
    try:
        return _archive_response(service.prepare_skill_archive(name))
    except SkillsServiceError as exc:
        message = str(exc)
        raise HTTPException(status_code=exc.status_code, detail=message) from exc
    except Exception as exc:
        logger.error(str(exc), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to prepare skill archive",
        ) from exc


@router.get("/skills")
async def list_skills(
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(service.get_skills)


@router.post("/skills")
async def upload_skill(
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    async def _operation():
        return await service.upload_skill(await single_upload(request))

    return await _run(_operation)


@router.post("/skills/batch")
async def upload_skills_batch(
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    async def _operation():
        _, files = await multipart_parts(request)
        return await service.batch_upload_skills(files.getlist("files"))

    return await _run(_operation)


@router.patch("/skills/by-name")
async def update_skill_by_name(
    payload: SkillByNameUpdateRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    skill_name = _required_text(payload.skill_name, "skill_name")
    return await _run(
        lambda: service.update_skill(
            {
                "name": skill_name,
                "active": payload.active_value(),
            }
        )
    )


@router.delete("/skills/by-name")
async def delete_skill_by_name(
    skill_name: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.delete_skill({"name": skill_name}))


@router.get("/skills/archive")
async def download_skill_by_name(
    skill_name: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _download_skill(service, skill_name)


@router.get("/skills/files")
async def list_skill_files_by_name(
    request: Request,
    skill_name: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(
        lambda: service.list_skill_files(
            skill_name,
            request.query_params.get("path", ""),
        )
    )


@router.get("/skills/file")
async def get_skill_file_by_name(
    skill_name: str,
    path: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.get_skill_file(skill_name, path))


@router.put("/skills/file")
async def update_skill_file_by_name(
    payload: SkillFileUpdateRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    skill_name = _required_text(payload.skill_name, "skill_name")
    path = _required_text(payload.path, "path")
    return await _run(
        lambda: service.update_skill_file(
            {
                "name": skill_name,
                "path": path,
                "content": payload.content,
            }
        )
    )


@router.get("/skills/{skill_name:path}/archive")
async def download_skill(
    skill_name: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _download_skill(service, skill_name)


@router.get("/skills/{skill_name:path}/files")
async def list_skill_files(
    skill_name: str,
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(
        lambda: service.list_skill_files(
            skill_name,
            request.query_params.get("path", ""),
        )
    )


@router.get("/skills/{skill_name:path}/files/{file_path:path}")
async def get_skill_file(
    skill_name: str,
    file_path: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.get_skill_file(skill_name, file_path))


@router.put("/skills/{skill_name:path}/files/{file_path:path}")
async def update_skill_file(
    skill_name: str,
    file_path: str,
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    content = (await request.body()).decode("utf-8")
    return await _run(
        lambda: service.update_skill_file(
            {"name": skill_name, "path": file_path, "content": content}
        )
    )


@router.patch("/skills/{skill_name:path}")
async def update_skill(
    skill_name: str,
    payload: SkillUpdateRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(
        lambda: service.update_skill(
            {
                "name": skill_name,
                "active": payload.active_value(),
            }
        )
    )


@router.delete("/skills/{skill_name:path}")
async def delete_skill(
    skill_name: str,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.delete_skill({"name": skill_name}))


@router.get("/skills/neo/candidates")
async def list_neo_skill_candidates(
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(
        service.get_neo_candidates(
            dict(request.query_params),
        )
    )


@router.get("/skills/neo/releases")
async def list_neo_skill_releases(
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(
        service.get_neo_releases(
            dict(request.query_params),
        )
    )


@router.get("/skills/neo/payload")
async def get_neo_skill_payload(
    request: Request,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(service.get_neo_payload(dict(request.query_params)))


@router.post("/skills/neo/evaluate")
async def evaluate_neo_skill_candidate(
    payload: SkillNeoRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.evaluate_neo_candidate(_model_dict(payload)))


@router.post("/skills/neo/promote")
async def promote_neo_skill_candidate(
    payload: SkillNeoRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.promote_neo_candidate(_model_dict(payload)))


@router.post("/skills/neo/rollback")
async def rollback_neo_skill_release(
    payload: SkillNeoRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.rollback_neo_release(_model_dict(payload)))


@router.post("/skills/neo/sync")
async def sync_neo_skill_release(
    payload: SkillNeoRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.sync_neo_release(_model_dict(payload)))


@router.post("/skills/neo/candidates/delete")
async def delete_neo_skill_candidate(
    payload: SkillNeoRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.delete_neo_candidate(_model_dict(payload)))


@router.post("/skills/neo/releases/delete")
async def delete_neo_skill_release(
    payload: SkillNeoRequest,
    _auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.delete_neo_release(_model_dict(payload)))


@legacy_router.get("")
async def list_dashboard_skills(
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _run(service.get_skills)


@legacy_router.post("/upload")
async def upload_dashboard_skill(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    async def _operation():
        return await service.upload_skill(await single_upload(request))

    return await _run(_operation)


@legacy_router.post("/batch-upload")
async def batch_upload_dashboard_skills(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    async def _operation():
        _, files = await multipart_parts(request)
        return await service.batch_upload_skills(files.getlist("files"))

    return await _run(_operation)


@legacy_router.get("/download")
async def download_dashboard_skill(
    name: str,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _download_skill(service, name)


@legacy_router.get("/files")
async def list_dashboard_skill_files(
    request: Request,
    name: str,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _run(
        lambda: service.list_skill_files(name, request.query_params.get("path", ""))
    )


@legacy_router.get("/file")
async def get_dashboard_skill_file(
    name: str,
    path: str = "SKILL.md",
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _run(lambda: service.get_skill_file(name, path))


@legacy_router.post("/file")
async def update_dashboard_skill_file(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_skill_file(body))


@legacy_router.post("/update")
async def update_dashboard_skill(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_skill(body))


@legacy_router.post("/delete")
async def delete_dashboard_skill(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_skill(body))


@legacy_router.get("/neo/candidates")
async def list_dashboard_neo_skill_candidates(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _run(service.get_neo_candidates(dict(request.query_params)))


@legacy_router.get("/neo/releases")
async def list_dashboard_neo_skill_releases(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _run(service.get_neo_releases(dict(request.query_params)))


@legacy_router.get("/neo/payload")
async def get_dashboard_neo_skill_payload(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    return await _run(service.get_neo_payload(dict(request.query_params)))


@legacy_router.post("/neo/evaluate")
async def evaluate_dashboard_neo_skill_candidate(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.evaluate_neo_candidate(body))


@legacy_router.post("/neo/promote")
async def promote_dashboard_neo_skill_candidate(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.promote_neo_candidate(body))


@legacy_router.post("/neo/rollback")
async def rollback_dashboard_neo_skill_release(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.rollback_neo_release(body))


@legacy_router.post("/neo/sync")
async def sync_dashboard_neo_skill_release(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.sync_neo_release(body))


@legacy_router.post("/neo/delete-candidate")
async def delete_dashboard_neo_skill_candidate(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_neo_candidate(body))


@legacy_router.post("/neo/delete-release")
async def delete_dashboard_neo_skill_release(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: SkillsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_neo_release(body))
