"""
Tools Public API for AstrBot.

This module provides a simple, stable interface for tool registration
and management. All implementations are delegated to the _internal package.

Example:
    from astrbot.api.tools import tool, get_registry

    @tool(name="weather", description="Get weather", parameters={...})
    async def get_weather(city: str) -> str:
        return f"Weather in {city} is sunny"

    registry = get_registry()
    tools = registry.list_tools()
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

# Import from _internal package (the canonical source)
from astrbot._internal.tools.base import FunctionTool, ToolSchema, ToolSet
from astrbot._internal.tools.registry import FunctionToolManager

__all__ = ["FunctionTool", "ToolRegistry", "ToolSet", "get_registry", "tool", "ToolSchema"]


class ToolRegistry:
    """Wrapper around FunctionToolManager for simplified tool registration.

    This class provides a user-friendly interface for registering and
    managing tools, delegating to the internal FunctionToolManager.
    """

    _instance: ToolRegistry | None = None

    def __init__(self) -> None:
        # Import here to avoid circular imports
        from astrbot.core.provider.register import llm_tools as func_tool_manager

        self._manager: FunctionToolManager = func_tool_manager

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        """Get the singleton ToolRegistry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool: FunctionTool) -> None:
        """Register a FunctionTool."""
        self._manager.func_list.append(tool)

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name. Returns True if found and removed."""
        for i, f in enumerate(self._manager.func_list):
            if f.name == name:
                self._manager.func_list.pop(i)
                return True
        return False

    def list_tools(self) -> list[ToolSchema]:
        """List all registered tools."""
        return self._manager.func_list.copy()

    def get_tool(self, name: str) -> ToolSchema | None:
        """Get a tool by name."""
        return self._manager.get_func(name)


def get_registry() -> ToolRegistry:
    """Get the global ToolRegistry instance."""
    return ToolRegistry.get_instance()


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
) -> Callable[
    [Callable[..., Awaitable[str | None]]], Callable[..., Awaitable[str | None]]
]:
    """Decorator to register an async function as a tool.

    Args:
        name: Tool name (used by LLM to invoke it)
        description: What the tool does
        parameters: JSON Schema for parameters (optional)

    Example:
        @tool(name="weather", description="Get weather for a city", parameters={...})
        async def get_weather(city: str) -> str:
            return f"The weather in {city} is sunny"
    """
    if parameters is None:
        parameters = {"type": "object", "properties": {}}

    def decorator(
        func: Callable[..., Awaitable[str | None]],
    ) -> Callable[..., Awaitable[str | None]]:
        func_tool = FunctionTool(
            name=name,
            description=description,
            parameters=parameters,
            handler=func,
            handler_module_path=getattr(func, "__module__", ""),
            source="api",
        )
        get_registry().register(func_tool)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> str | None:
            return await func(*args, **kwargs)

        return wrapper

    return decorator
