from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.services.sandbox import SandboxService, SandboxServiceError
from astrbot.dashboard.services.sandbox_helpers import (
    DEMO_MODE_ERROR_MESSAGE,
    is_demo_mode,
)

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
    return await require_scope(request, "sandbox")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except SandboxServiceError as exc:
        return error(exc.public_message)


def _session_id(session_id: str | None) -> str:
    return session_id or "dashboard"


def _demo_mode_error():
    if is_demo_mode():
        return error(DEMO_MODE_ERROR_MESSAGE)
    return None


@legacy_router.get("/providers")
async def list_providers(
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(lambda: service.list_providers(_session_id(session_id)))


@legacy_router.get("")
async def list_sandboxes(
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(service.list_sandboxes)


@legacy_router.get("/current")
async def get_current_sandbox(
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    return await _run(lambda: service.get_current_sandbox(_session_id(session_id)))


@legacy_router.delete("/current")
async def release_current_sandbox(
    session_id: str | None = Query(default=None),
    sandbox_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    return await _run(
        lambda: service.release_current_sandbox(_session_id(session_id), sandbox_id)
    )


@legacy_router.post("")
async def create_sandbox(
    request: Request,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    data = await _json_or_empty(request)
    return await _run(lambda: service.create_sandbox(_session_id(session_id), data))


@legacy_router.post("/{sandbox_id}/switch")
async def switch_sandbox(
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    return await _run(
        lambda: service.switch_sandbox(_session_id(session_id), sandbox_id)
    )


@legacy_router.post("/{sandbox_id}/takeover")
async def takeover_sandbox(
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    return await _run(
        lambda: service.takeover_sandbox(_session_id(session_id), sandbox_id)
    )


@legacy_router.post("/{sandbox_id}/default")
async def set_default_sandbox(
    sandbox_id: str,
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    return await _run(lambda: service.set_default_sandbox(sandbox_id))


@legacy_router.post("/{sandbox_id}/shell")
async def run_shell(
    sandbox_id: str,
    request: Request,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    data = await _json_or_empty(request)
    return await _run(
        lambda: service.run_shell(_session_id(session_id), sandbox_id, data)
    )


@legacy_router.post("/{sandbox_id}/screenshot")
async def capture_screenshot(
    sandbox_id: str,
    request: Request,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    data = await _json_or_empty(request)
    return await _run(
        lambda: service.capture_screenshot(_session_id(session_id), sandbox_id, data)
    )


@legacy_router.patch("/{sandbox_id}")
async def update_sandbox(
    sandbox_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    data = await _json_or_empty(request)
    return await _run(lambda: service.update_sandbox(sandbox_id, data))


@legacy_router.delete("/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: str,
    session_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_sandbox_scope),
    service: SandboxService = Depends(get_service),
):
    if demo_response := _demo_mode_error():
        return demo_response
    return await _run(
        lambda: service.destroy_sandbox(_session_id(session_id), sandbox_id)
    )
