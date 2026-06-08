from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from astrbot.dashboard.services.t2i_service import T2iService, T2iServiceError

from .auth import AuthContext, require_dashboard_user, require_scope
from .responses import ApiError, ok
from .schemas import T2iActiveTemplateRequest, T2iTemplateRequest

router = APIRouter(tags=["Text To Image"])
dashboard_router = APIRouter(
    prefix="/api/t2i",
    tags=["Dashboard Text To Image"],
    include_in_schema=False,
)


def get_service(request: Request) -> T2iService:
    return request.app.state.services.t2i


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


async def _json_or_empty(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _raise_t2i_error(exc: T2iServiceError) -> None:
    raise ApiError(str(exc), status_code=exc.status_code) from exc


def _response(
    data=None,
    *,
    message: str | None = None,
    status_code: int = 200,
):
    payload = ok(data, message)
    if status_code == 200:
        return payload
    return JSONResponse(payload, status_code=status_code)


async def _run(
    operation,
    *,
    message: str | None = None,
    status_code: int = 200,
    result_as_message: bool = False,
):
    try:
        result = operation() if callable(operation) else operation
        while hasattr(result, "__await__"):
            result = await result
        if isinstance(result, tuple):
            payload, result_message = result
            return _response(payload, message=result_message)
        if result_as_message:
            return _response(message=str(result), status_code=status_code)
        return _response(result, message=message, status_code=status_code)
    except T2iServiceError as exc:
        _raise_t2i_error(exc)


@router.get("/t2i/templates")
async def list_t2i_templates(
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(service.list_templates)


@router.post("/t2i/templates")
async def create_t2i_template(
    payload: T2iTemplateRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(
        lambda: service.create_template(payload.name, payload.content),
        message="Template created successfully.",
        status_code=201,
    )


@router.get("/t2i/templates/active")
async def get_active_t2i_template(
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(service.get_active_template)


@router.put("/t2i/templates/active")
async def set_active_t2i_template(
    payload: T2iActiveTemplateRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(
        lambda: service.set_active_template(payload.name),
        result_as_message=True,
    )


@router.post("/t2i/templates/default/reset")
async def reset_default_t2i_template(
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(
        service.reset_default_template,
        result_as_message=True,
    )


@router.get("/t2i/templates/{name:path}")
async def get_t2i_template(
    name: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(lambda: service.get_template(name))


@router.put("/t2i/templates/{name:path}")
async def update_t2i_template(
    name: str,
    payload: T2iTemplateRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(lambda: service.update_template(name, payload.content))


@router.delete("/t2i/templates/{name:path}")
async def delete_t2i_template(
    name: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: T2iService = Depends(get_service),
):
    return await _run(
        lambda: service.delete_template(name),
        message="Template deleted successfully.",
    )


@dashboard_router.get("/templates")
async def list_dashboard_t2i_templates(
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    return await _run(service.list_templates)


@dashboard_router.get("/templates/active")
async def get_dashboard_active_t2i_template(
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    return await _run(service.get_active_template)


@dashboard_router.post("/templates/create")
async def create_dashboard_t2i_template(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(
        lambda: service.create_template(body.get("name"), body.get("content")),
        message="Template created successfully.",
        status_code=201,
    )


@dashboard_router.post("/templates/reset_default")
async def reset_dashboard_default_t2i_template(
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    return await _run(service.reset_default_template, result_as_message=True)


@dashboard_router.post("/templates/set_active")
async def set_dashboard_active_t2i_template(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(
        lambda: service.set_active_template(body.get("name")),
        result_as_message=True,
    )


@dashboard_router.get("/templates/{name:path}")
async def get_dashboard_t2i_template(
    name: str,
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    return await _run(lambda: service.get_template(name))


@dashboard_router.put("/templates/{name:path}")
async def update_dashboard_t2i_template(
    name: str,
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_template(name, body.get("content")))


@dashboard_router.delete("/templates/{name:path}")
async def delete_dashboard_t2i_template(
    name: str,
    _username: str = Depends(require_dashboard_user),
    service: T2iService = Depends(get_service),
):
    return await _run(
        lambda: service.delete_template(name),
        message="Template deleted successfully.",
    )
