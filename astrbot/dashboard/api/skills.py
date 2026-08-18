from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from astrbot import logger
from astrbot.core.auth.models import Resource
from astrbot.core.utils.error_redaction import safe_error
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, error, ok
from astrbot.dashboard.schemas import (
    SkillNeoRequest,
    SkillUpdateRequest,
)
from astrbot.dashboard.services.skills_service import (
    SkillArchive,
    SkillsOperationResult,
    SkillsService,
    SkillsServiceError,
)

from .auth import AuthContext, object_resource, require_resource_action, require_scope
from .error_handling import internal_error_response

router = APIRouter(tags=["Skills"])
_ARCHIVE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Skill archive",
        "content": {
            "application/zip": {"schema": {"type": "string", "format": "binary"}}
        },
    }
}


def get_service(request: Request) -> SkillsService:
    return request.app.state.services.skills


async def require_skill_scope(request: Request) -> AuthContext:
    return await require_scope(request, "skill")


async def _authorize_skill_collection(
    request: Request, auth: AuthContext, *, write: bool
) -> None:
    await require_resource_action(
        request,
        auth,
        action="extension.manage" if write else "extension.read",
        resource=Resource.named("skill", "collection"),
    )


async def _authorize_skill_object(
    request: Request, auth: AuthContext, skill_name: str, *, write: bool
) -> None:
    await require_resource_action(
        request,
        auth,
        action="extension.manage" if write else "extension.read",
        resource=object_resource("skill", skill_name),
    )


async def _authorize_neo_collection(
    request: Request, auth: AuthContext, *, kind: str, write: bool = False
) -> None:
    await require_resource_action(
        request,
        auth,
        action="extension.manage" if write else "extension.read",
        resource=Resource.named("skill", f"neo-{kind}"),
    )


async def _authorize_neo_object(
    request: Request,
    auth: AuthContext,
    *,
    kind: str,
    object_id: str | None,
    write: bool,
) -> None:
    if not object_id or not str(object_id).strip():
        raise ApiError("Authorization denied", status_code=403)
    await require_resource_action(
        request,
        auth,
        action="extension.manage" if write else "extension.read",
        resource=object_resource("skill", f"neo-{kind}", str(object_id).strip()),
    )


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


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        if isinstance(result, SkillsOperationResult):
            return _serialize_result(result)
        return ok(result)
    except SkillsServiceError as exc:
        return error(str(exc))
    except Exception as exc:
        return internal_error_response(logger, "Skill operation failed", exc)


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
        logger.error("Failed to prepare skill archive: %s", safe_error("", exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to prepare skill archive",
        ) from exc


@router.get("/skills")
async def list_skills(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_collection(request, auth, write=False)
    return await _run(service.get_skills)


@router.post("/skills")
async def upload_skill(
    request: Request,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_collection(request, auth, write=True)
    return await _run(lambda: service.upload_skill(file))


@router.post("/skills/batch")
async def upload_skills_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_collection(request, auth, write=True)
    return await _run(lambda: service.batch_upload_skills(files))


@router.get("/skills/{skill_name:path}/archive", responses=_ARCHIVE_RESPONSE)
async def download_skill(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_object(request, auth, skill_name, write=False)
    return await _download_skill(service, skill_name)


@router.get("/skills/{skill_name:path}/files")
async def list_skill_files(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_object(request, auth, skill_name, write=False)
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
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_object(request, auth, skill_name, write=False)
    return await _run(lambda: service.get_skill_file(skill_name, file_path))


@router.put("/skills/{skill_name:path}/files/{file_path:path}")
async def update_skill_file(
    skill_name: str,
    file_path: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_object(request, auth, skill_name, write=True)
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
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_object(request, auth, skill_name, write=True)
    return await _run(
        lambda: service.update_skill(
            {
                "name": skill_name,
                "active": payload.active,
            }
        )
    )


@router.delete("/skills/{skill_name:path}")
async def delete_skill(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_skill_object(request, auth, skill_name, write=True)
    return await _run(lambda: service.delete_skill({"name": skill_name}))


@router.get("/skills/neo/candidates")
async def list_neo_skill_candidates(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_collection(request, auth, kind="candidates")
    return await _run(
        service.get_neo_candidates(
            dict(request.query_params),
        )
    )


@router.get("/skills/neo/releases")
async def list_neo_skill_releases(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_collection(request, auth, kind="releases")
    return await _run(
        service.get_neo_releases(
            dict(request.query_params),
        )
    )


@router.get("/skills/neo/payload")
async def get_neo_skill_payload(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_object(
        request,
        auth,
        kind="payload",
        object_id=request.query_params.get("payload_ref"),
        write=False,
    )
    return await _run(service.get_neo_payload(dict(request.query_params)))


@router.post("/skills/neo/evaluate")
async def evaluate_neo_skill_candidate(
    payload: SkillNeoRequest,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_object(
        request, auth, kind="candidate", object_id=payload.candidate_id, write=True
    )
    return await _run(lambda: service.evaluate_neo_candidate(_model_dict(payload)))


@router.post("/skills/neo/promote")
async def promote_neo_skill_candidate(
    payload: SkillNeoRequest,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_object(
        request, auth, kind="candidate", object_id=payload.candidate_id, write=True
    )
    return await _run(lambda: service.promote_neo_candidate(_model_dict(payload)))


@router.post("/skills/neo/rollback")
async def rollback_neo_skill_release(
    payload: SkillNeoRequest,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_object(
        request, auth, kind="release", object_id=payload.release_id, write=True
    )
    return await _run(lambda: service.rollback_neo_release(_model_dict(payload)))


@router.post("/skills/neo/sync")
async def sync_neo_skill_release(
    payload: SkillNeoRequest,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    if payload.release_id:
        target_kind = "release"
        target_id = payload.release_id
    else:
        target_kind = "skill-key"
        target_id = payload.skill_key
    await _authorize_neo_object(
        request, auth, kind=target_kind, object_id=target_id, write=True
    )
    return await _run(lambda: service.sync_neo_release(_model_dict(payload)))


@router.post("/skills/neo/candidates/delete")
async def delete_neo_skill_candidate(
    payload: SkillNeoRequest,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_object(
        request, auth, kind="candidate", object_id=payload.candidate_id, write=True
    )
    return await _run(lambda: service.delete_neo_candidate(_model_dict(payload)))


@router.post("/skills/neo/releases/delete")
async def delete_neo_skill_release(
    payload: SkillNeoRequest,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    service: SkillsService = Depends(get_service),
):
    await _authorize_neo_object(
        request, auth, kind="release", object_id=payload.release_id, write=True
    )
    return await _run(lambda: service.delete_neo_release(_model_dict(payload)))
