from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    PersonaByIdRequest,
    PersonaFolderRequest,
    PersonaMoveRequest,
    PersonaReorderRequest,
    PersonaRequest,
)
from astrbot.dashboard.services.persona_service import (
    PersonaService,
    PersonaServiceError,
)

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["Personas"])
legacy_router = APIRouter(
    prefix="/api/persona",
    tags=["Dashboard Personas"],
    include_in_schema=False,
)


def get_service(request: Request) -> PersonaService:
    return request.app.state.services.personas


async def require_persona_scope(request: Request) -> AuthContext:
    return await require_scope(request, "persona")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _model_dict(payload) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def _raise_persona_error(exc: PersonaServiceError | ValueError) -> None:
    raise ApiError(str(exc)) from exc


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except (PersonaServiceError, ValueError) as exc:
        _raise_persona_error(exc)


@router.get("/personas/tree")
async def persona_tree(
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(service.get_folder_tree)


@router.get("/personas")
async def list_personas(
    request: Request,
    folder_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(
        lambda: service.list_personas(folder_id, "folder_id" in request.query_params)
    )


@router.post("/personas")
async def create_persona(
    payload: PersonaRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.create_persona(_model_dict(payload)))


@router.get("/personas/by-id")
async def get_persona_by_id(
    persona_id: str = Query(...),
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.get_persona_detail({"persona_id": persona_id}))


@router.put("/personas/by-id")
async def update_persona_by_id(
    payload: PersonaByIdRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.update_persona(_model_dict(payload)))


@router.delete("/personas/by-id")
async def delete_persona_by_id(
    persona_id: str = Query(...),
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.delete_persona({"persona_id": persona_id}))


@router.post("/personas/move")
async def move_persona(
    payload: PersonaMoveRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.move_persona(_model_dict(payload)))


@router.post("/personas/reorder")
async def reorder_personas(
    payload: PersonaReorderRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.reorder_items(_model_dict(payload)))


@router.get("/persona-folders")
async def list_persona_folders(
    parent_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.list_folders(parent_id))


@router.post("/persona-folders")
async def create_persona_folder(
    payload: PersonaFolderRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.create_folder(_model_dict(payload)))


@router.put("/persona-folders/{folder_id:path}")
async def update_persona_folder(
    folder_id: str,
    payload: PersonaFolderRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(
        lambda: service.update_folder({"folder_id": folder_id, **_model_dict(payload)})
    )


@router.delete("/persona-folders/{folder_id:path}")
async def delete_persona_folder(
    folder_id: str,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.delete_folder({"folder_id": folder_id}))


@router.get("/personas/{persona_id:path}")
async def get_persona(
    persona_id: str,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.get_persona_detail({"persona_id": persona_id}))


@router.put("/personas/{persona_id:path}")
async def update_persona(
    persona_id: str,
    payload: PersonaRequest,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(
        lambda: service.update_persona(
            {"persona_id": persona_id, **_model_dict(payload)}
        )
    )


@router.delete("/personas/{persona_id:path}")
async def delete_persona(
    persona_id: str,
    _auth: AuthContext = Depends(require_persona_scope),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.delete_persona({"persona_id": persona_id}))


@legacy_router.get("/list")
async def list_dashboard_personas(
    request: Request,
    folder_id: str | None = Query(default=None),
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    return await _run(
        lambda: service.list_personas(folder_id, "folder_id" in request.query_params)
    )


@legacy_router.post("/detail")
async def get_dashboard_persona_detail(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.get_persona_detail(body))


@legacy_router.post("/create")
async def create_dashboard_persona(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.create_persona(body))


@legacy_router.post("/update")
async def update_dashboard_persona(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_persona(body))


@legacy_router.post("/delete")
async def delete_dashboard_persona(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_persona(body))


@legacy_router.post("/move")
async def move_dashboard_persona(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.move_persona(body))


@legacy_router.post("/reorder")
async def reorder_dashboard_personas(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.reorder_items(body))


@legacy_router.get("/folder/list")
async def list_dashboard_persona_folders(
    parent_id: str | None = Query(default=None),
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    return await _run(lambda: service.list_folders(parent_id))


@legacy_router.get("/folder/tree")
async def get_dashboard_persona_folder_tree(
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    return await _run(service.get_folder_tree)


@legacy_router.post("/folder/detail")
async def get_dashboard_persona_folder_detail(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.get_folder_detail(body))


@legacy_router.post("/folder/create")
async def create_dashboard_persona_folder(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.create_folder(body))


@legacy_router.post("/folder/update")
async def update_dashboard_persona_folder(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_folder(body))


@legacy_router.post("/folder/delete")
async def delete_dashboard_persona_folder(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PersonaService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_folder(body))
