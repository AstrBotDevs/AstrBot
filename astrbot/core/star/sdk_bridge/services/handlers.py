from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound

from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)

if TYPE_CHECKING:
    from ..bridge import SDKPluginBridge


class HandlerRegisterService:
    """Serve the handler.register capability (legacy register_commands).

    Mirrors core Context.register_commands: build one StarHandlerMetadata
    with a CommandFilter (or RegexFilter when use_regex is set) whose stub
    RPC-invokes the handler the plugin registered at runtime.
    """

    capability_id = "handler.register"

    def __init__(self, bridge: SDKPluginBridge) -> None:
        """Initialize the service with the owning bridge."""
        self._bridge = bridge

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the register operation."""
        if operation != "register":
            raise NotFound(f"unknown handler.register operation: {operation}")
        handler_id = payload.get("handler_id")
        command_name = payload.get("command_name")
        if not isinstance(handler_id, str) or not handler_id:
            raise InvalidRequest("register requires a handler_id")
        if not isinstance(command_name, str) or not command_name:
            raise InvalidRequest("register requires a command_name")
        use_regex = bool(payload.get("use_regex", False))

        bridge = self._bridge
        full_name = f"{bridge.module_path}_{handler_id}"
        handler_md = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=full_name,
            handler_name=handler_id,
            handler_module_path=bridge.module_path,
            handler=bridge._make_command_stub(handler_id, command_name),
            event_filters=[],
            desc=str(payload.get("desc") or ""),
        )
        if use_regex:
            from astrbot.core.star.filter.regex import RegexFilter

            handler_md.event_filters.append(RegexFilter(regex=command_name))
        else:
            from astrbot.core.star.filter.command import CommandFilter

            handler_md.event_filters.append(
                CommandFilter(command_name=command_name, handler_md=handler_md),
            )
        star_handlers_registry.append(handler_md)
        bridge._handler_full_names.append(full_name)
        return {"registered": True}
