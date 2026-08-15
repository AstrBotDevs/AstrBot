from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    BuiltinCommandBulkToggleRequest,
    CommandPermissionRequest,
    CommandRenameRequest,
    CommandToggleRequest,
    CommandUpdateRequest,
)
from astrbot.dashboard.services.command_service import (
    CommandService,
    CommandServiceError,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Extension Components"])


def get_command_service(request: Request) -> CommandService:
    return request.app.state.services.commands


async def require_tool_scope(request: Request) -> AuthContext:
    return await require_scope(request, "tool")


def _raise_command_error(exc: CommandServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _list_commands(config_id: str | None, service: CommandService):
    try:
        return ok(await service.list_commands(config_id or ""))
    except CommandServiceError as exc:
        _raise_command_error(exc)


async def _list_command_conflicts(service: CommandService):
    try:
        return ok(await service.list_conflicts())
    except CommandServiceError as exc:
        _raise_command_error(exc)


async def _toggle_command(payload: CommandToggleRequest, service: CommandService):
    try:
        return ok(
            await service.toggle_command(payload.handler_full_name, payload.enabled)
        )
    except CommandServiceError as exc:
        _raise_command_error(exc)


async def _bulk_toggle_builtin_commands(
    payload: BuiltinCommandBulkToggleRequest,
    service: CommandService,
):
    try:
        return ok(await service.bulk_toggle_builtin_commands(payload.enabled))
    except CommandServiceError as exc:
        _raise_command_error(exc)


async def _rename_command(payload: CommandRenameRequest, service: CommandService):
    try:
        return ok(
            await service.rename_command(
                payload.handler_full_name,
                payload.new_name,
                aliases=payload.aliases,
            )
        )
    except CommandServiceError as exc:
        _raise_command_error(exc)


async def _update_command_permission(
    payload: CommandPermissionRequest,
    service: CommandService,
):
    try:
        return ok(
            await service.update_permission(payload.handler_full_name, payload.action)
        )
    except CommandServiceError as exc:
        _raise_command_error(exc)


@router.get("/commands")
async def list_commands(
    config_id: str | None = None,
    _auth: AuthContext = Depends(require_tool_scope),
    service: CommandService = Depends(get_command_service),
):
    return await _list_commands(config_id, service)


@router.get("/commands/conflicts")
async def list_command_conflicts(
    _auth: AuthContext = Depends(require_tool_scope),
    service: CommandService = Depends(get_command_service),
):
    return await _list_command_conflicts(service)


@router.patch("/commands/builtin")
async def bulk_toggle_builtin_commands(
    payload: BuiltinCommandBulkToggleRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: CommandService = Depends(get_command_service),
):
    return await _bulk_toggle_builtin_commands(payload, service)


@router.patch("/commands/{command_id:path}")
async def update_command(
    command_id: str,
    payload: CommandUpdateRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: CommandService = Depends(get_command_service),
):
    if payload.enabled is not None:
        return await _toggle_command(
            CommandToggleRequest(
                handler_full_name=command_id,
                enabled=payload.enabled,
            ),
            service,
        )
    if payload.alias is not None:
        return await _rename_command(
            CommandRenameRequest(
                handler_full_name=command_id,
                new_name=payload.alias,
                aliases=payload.aliases,
            ),
            service,
        )
    return await _update_command_permission(
        CommandPermissionRequest(
            handler_full_name=command_id,
            action=payload.action or "",
        ),
        service,
    )
