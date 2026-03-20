from __future__ import annotations

from typing import Any

import pytest

from astrbot_sdk._internal.testing_support import MockContext
from astrbot_sdk.llm.entities import LLMToolSpec


class RecordingDispatcher:
    def __init__(self) -> None:
        self.added: list[dict[str, Any]] = []
        self.removed: list[tuple[str, str]] = []

    def add_dynamic_llm_tool(
        self,
        *,
        plugin_id: str,
        spec: LLMToolSpec,
        callable_obj,
        owner: Any | None = None,
    ) -> None:
        self.added.append(
            {
                "plugin_id": plugin_id,
                "spec": spec,
                "callable_obj": callable_obj,
                "owner": owner,
            }
        )

    def remove_llm_tool(self, plugin_id: str, name: str) -> bool:
        self.removed.append((plugin_id, name))
        return True


@pytest.mark.asyncio
async def test_register_llm_tool_keeps_manager_and_dispatcher_specs_aligned() -> None:
    ctx = MockContext()
    dispatcher = RecordingDispatcher()
    ctx.peer._sdk_capability_dispatcher = dispatcher

    async def echo_tool(text: str) -> str:
        return text

    names = await ctx.register_llm_tool(
        "echo",
        {"type": "object", "properties": {"text": {"type": "string"}}},
        "Echo the provided text",
        echo_tool,
        active=False,
    )

    assert names == ["echo"]
    registered = await ctx.get_llm_tool_manager().get("echo")
    assert registered is not None
    assert registered.name == "echo"
    assert registered.description == "Echo the provided text"
    assert registered.parameters_schema == {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }
    assert registered.handler_ref == "__dynamic_llm_tool__:echo"
    assert registered.active is False

    assert len(dispatcher.added) == 1
    added = dispatcher.added[0]
    assert added["plugin_id"] == "test-plugin"
    assert added["callable_obj"] is echo_tool
    assert added["owner"] is None
    assert added["spec"].model_dump() == registered.model_dump()

    removed = await ctx.unregister_llm_tool("echo")
    assert removed is True
    assert dispatcher.removed == [("test-plugin", "echo")]
    assert await ctx.get_llm_tool_manager().get("echo") is None
