from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from astrbot import logger
from astrbot.core.auth.models import Resource
from astrbot.core.utils.error_redaction import safe_error
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.schemas import PipInstallRequest
from astrbot.dashboard.services.update_service import (
    UpdateService,
    UpdateServiceError,
    UpdateServiceResult,
)

from .auth import AuthContext, require_resource_action, require_scope

router = APIRouter(tags=["Updates"])


def get_service(request: Request) -> UpdateService:
    return request.app.state.services.updates


async def _require_system_action(
    request: Request,
    *,
    action: str,
    resource_id: str,
) -> AuthContext:
    auth = await require_scope(request, "system", authorize_action=False)
    await require_resource_action(
        request,
        auth,
        action=action,
        resource=Resource.named("system", resource_id),
    )
    return auth


async def require_system_pip_install_scope(request: Request) -> AuthContext:
    return await _require_system_action(
        request,
        action="system.pip_install",
        resource_id="pip-install",
    )


def _model_dict(payload) -> dict:
    return payload.model_dump(exclude_none=True)


def _result_payload(result: UpdateServiceResult) -> dict:
    if result.status == "success":
        return {
            "status": "success",
            "message": result.message,
            "data": result.data,
        }
    return {
        "status": "ok",
        "message": result.message,
        "data": {} if result.data is None else result.data,
    }


def _service_response(result: UpdateServiceResult) -> JSONResponse:
    return JSONResponse(
        _result_payload(result),
        status_code=200,
        headers=result.headers or None,
    )


def _service_error(exc: UpdateServiceError) -> JSONResponse:
    logger.error("Dashboard pip install failed: %s", safe_error("", exc))
    return JSONResponse(
        {"status": "error", "message": "An internal error has occurred.", "data": None},
        status_code=200,
    )


async def _run(operation) -> JSONResponse:
    try:
        result = await run_maybe_async(operation)
        return _service_response(result)
    except UpdateServiceError as exc:
        return _service_error(exc)


@router.post("/pip/install")
async def install_pip_package(
    payload: PipInstallRequest,
    _auth: AuthContext = Depends(require_system_pip_install_scope),
    service: UpdateService = Depends(get_service),
):
    return await _run(lambda: service.install_pip_package(_model_dict(payload)))
