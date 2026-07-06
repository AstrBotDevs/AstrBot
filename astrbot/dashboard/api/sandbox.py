from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from astrbot.core import logger
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.services.sandbox import SandboxService, SandboxServiceError

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Sandbox"])
legacy_router = APIRouter(
    prefix="/api/sandbox",
    tags=["Dashboard Sandbox"],
    include_in_schema=False,
)


def get_service(request: Request) -> SandboxService:
    return request.app.state.services.sandbox


async def require_sandbox_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _session_id(session_id: str | None) -> str:
    return session_id or "dashboard"


async def _run(operation, message: str):
    try:
        result = operation()
        if hasattr(result, "__await__"):
            result = await result
        return ok(result)
    except SandboxServiceError as exc:
        return error(str(exc))
    except Exception as exc:
        logger.error("%s: %s", message, exc, exc_info=True)
        return error(f"{message}: {exc!s}")


@router.get("/sandbox/providers")
@legacy_router.get("/providers")
async def list_providers(
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.list_providers(_session_id(session_id)),
        "Failed to list sandbox providers",
    )


@router.get("/sandbox")
@legacy_router.get("")
async def list_sandboxes(
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(service.list_sandboxes, "Failed to list sandboxes")


@router.get("/sandbox/current")
@legacy_router.get("/current")
async def get_current_sandbox(
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.get_current_sandbox(_session_id(session_id)),
        "Failed to get current sandbox",
    )


@router.delete("/sandbox/current")
@legacy_router.delete("/current")
async def release_current_sandbox(
    session_id: str | None = Query(default=None),
    sandbox_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.release_current_sandbox(_session_id(session_id), sandbox_id),
        "Failed to release sandbox",
    )


@router.post("/sandbox")
@legacy_router.post("")
async def create_sandbox(
    request: Request,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    data = await _json_or_empty(request)
    provider_id = str(data.get("provider_id") or "").strip()
    return await _run(
        lambda: service.create_sandbox(
            _session_id(session_id),
            provider_id,
            data.get("sandbox_name"),
        ),
        "Failed to create sandbox",
    )


@router.post("/sandbox/{sandbox_id}/switch")
@legacy_router.post("/{sandbox_id}/switch")
async def switch_sandbox(
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.switch_sandbox(_session_id(session_id), sandbox_id),
        "Failed to switch sandbox",
    )


@router.post("/sandbox/{sandbox_id}/takeover")
@legacy_router.post("/{sandbox_id}/takeover")
async def takeover_sandbox(
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.takeover_sandbox(_session_id(session_id), sandbox_id),
        "Failed to takeover sandbox",
    )


@router.post("/sandbox/{sandbox_id}/default")
@legacy_router.post("/{sandbox_id}/default")
async def set_default_sandbox(
    sandbox_id: str,
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.set_default_sandbox(sandbox_id),
        "Failed to set default sandbox",
    )


@router.post("/sandbox/{sandbox_id}/shell")
@legacy_router.post("/{sandbox_id}/shell")
async def run_shell(
    request: Request,
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    data = await _json_or_empty(request)
    return await _run(
        lambda: service.run_shell(_session_id(session_id), sandbox_id, data),
        "Failed to run sandbox shell",
    )


@router.post("/sandbox/{sandbox_id}/screenshot")
@legacy_router.post("/{sandbox_id}/screenshot")
async def capture_screenshot(
    request: Request,
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    data = await _json_or_empty(request)
    return await _run(
        lambda: service.capture_screenshot(_session_id(session_id), sandbox_id, data),
        "Failed to capture sandbox screenshot",
    )


@router.patch("/sandbox/{sandbox_id}")
@legacy_router.patch("/{sandbox_id}")
async def update_sandbox(
    request: Request,
    sandbox_id: str,
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    data = await _json_or_empty(request)
    return await _run(
        lambda: service.update_sandbox(sandbox_id, data),
        "Failed to update sandbox",
    )


@router.delete("/sandbox/{sandbox_id}")
@legacy_router.delete("/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(
        lambda: service.destroy_sandbox(_session_id(session_id), sandbox_id),
        "Failed to destroy sandbox",
    )
