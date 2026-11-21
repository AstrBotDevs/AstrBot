from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.tools import ToolDefinition

from astrbot.core.provider.register import llm_tools
from astrbot.core.star.star import star_map


class ToolRegisterService:
    """Serve the llm.tool.register capability for dynamic tool registration."""

    capability_id = "llm.tool.register"

    def __init__(self, make_stub: Any, track: Any, module_path: str) -> None:
        """Initialize the service.

        Args:
            make_stub: Factory building the executor stub for a handler ID.
            track: Callback recording tool names for cleanup on unload.
            module_path: Bridge module path of the owning plugin, used to
                attribute registered tools to the plugin in star_map.
        """
        self._make_stub = make_stub
        self._track = track
        self._module_path = module_path
        self._runtime_tool_names: list[str] = []

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve register/unregister/replace_runtime/toggle operations."""
        if operation == "register":
            definition = payload.get("definition")
            handler_id = payload.get("handler_id")
            if not isinstance(definition, ToolDefinition):
                raise InvalidRequest("register requires a ToolDefinition")
            if not isinstance(handler_id, str) or not handler_id:
                raise InvalidRequest("register requires a handler_id")
            func_args = [
                {
                    "type": param.type,
                    "name": param.name,
                    "description": param.description,
                }
                for param in definition.params
            ]
            llm_tools.add_func(
                definition.name,
                func_args,
                definition.description,
                self._make_stub(handler_id),
            )
            func_tool = llm_tools.get_func(definition.name)
            if func_tool is not None:
                # Attribute the tool to this plugin so plugin-level tool
                # listing, activation, and toggles apply (same as static
                # handshake tools and in-process context.add_llm_tools).
                func_tool.handler_module_path = self._module_path
            self._track(definition.name)
            return {}
        if operation == "unregister":
            name = payload.get("name")
            if not isinstance(name, str) or not name:
                raise InvalidRequest("unregister requires a tool name")
            llm_tools.remove_func(name)
            return {}
        if operation == "replace_runtime":
            raw_tools = payload.get("tools")
            if not isinstance(raw_tools, list):
                raise InvalidRequest("replace_runtime requires a tools list")
            for old_name in self._runtime_tool_names:
                llm_tools.remove_func(old_name)
            self._runtime_tool_names.clear()
            for item in raw_tools:
                if not isinstance(item, dict):
                    raise InvalidRequest(
                        "replace_runtime entry must be a dict",
                    )
                definition = item.get("definition")
                handler_id = item.get("handler_id")
                if not isinstance(definition, ToolDefinition):
                    raise InvalidRequest(
                        "replace_runtime requires a ToolDefinition",
                    )
                if not isinstance(handler_id, str) or not handler_id:
                    raise InvalidRequest(
                        "replace_runtime requires a handler_id",
                    )
                func_args = [
                    {
                        "type": param.type,
                        "name": param.name,
                        "description": param.description,
                    }
                    for param in definition.params
                ]
                llm_tools.add_func(
                    definition.name,
                    func_args,
                    definition.description,
                    self._make_stub(handler_id),
                )
                func_tool = llm_tools.get_func(definition.name)
                if func_tool is not None:
                    func_tool.handler_module_path = self._module_path
                self._track(definition.name)
                self._runtime_tool_names.append(definition.name)
            return {}
        if operation in ("activate", "deactivate"):
            name = payload.get("name")
            if not isinstance(name, str) or not name:
                raise InvalidRequest(f"{operation} requires a tool name")
            if operation == "activate":
                activated = await llm_tools.activate_llm_tool_async(name, star_map)
                return {"activated": bool(activated)}
            deactivated = await llm_tools.deactivate_llm_tool_async(name)
            return {"deactivated": bool(deactivated)}
        raise NotFound(f"unknown tool operation: {operation}")
