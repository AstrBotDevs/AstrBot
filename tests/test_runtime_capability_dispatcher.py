from __future__ import annotations

import json
import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from astrbot_sdk._internal.testing_support import MockCapabilityRouter, MockPeer
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.protocol.descriptors import CapabilityDescriptor
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime._streaming import StreamExecution
from astrbot_sdk.runtime.capability_dispatcher import CapabilityDispatcher
from astrbot_sdk.runtime.loader import LoadedCapability, LoadedLLMTool


class _SerializableChunk(BaseModel):
    value: str


def _build_loaded_capability(
    handler,
    *,
    name: str = "test.echo",
    plugin_id: str = "test-plugin",
) -> LoadedCapability:
    return LoadedCapability(
        descriptor=CapabilityDescriptor(
            name=name,
            description="test capability",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            supports_stream=True,
            cancelable=True,
        ),
        callable=handler,
        owner=object(),
        plugin_id=plugin_id,
    )


@pytest.mark.asyncio
async def test_capability_dispatcher_returns_stream_execution_for_async_generator() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())

    async def stream_capability(payload: dict[str, Any]):
        yield {"value": str(payload["name"]).upper()}
        yield _SerializableChunk(value="done")

    dispatcher = CapabilityDispatcher(
        plugin_id="test-plugin",
        peer=peer,
        capabilities=[_build_loaded_capability(stream_capability)],
    )

    execution = await dispatcher.invoke(
        InvokeMessage(
            id="req-stream",
            capability="test.echo",
            input={"name": "alice"},
            stream=True,
        ),
        CancelToken(),
    )

    assert isinstance(execution, StreamExecution)
    chunks = [chunk async for chunk in execution.iterator]

    assert chunks == [{"value": "ALICE"}, {"value": "done"}]
    assert execution.finalize(chunks) == {"items": chunks}


@pytest.mark.asyncio
async def test_capability_dispatcher_injection_error_mentions_supported_sources() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())

    def broken(required_name: str) -> dict[str, Any]:
        return {"ok": True}

    dispatcher = CapabilityDispatcher(
        plugin_id="plugin-alpha",
        peer=peer,
        capabilities=[
            _build_loaded_capability(
                broken,
                name="plugin-alpha.broken",
                plugin_id="plugin-alpha",
            )
        ],
    )

    with pytest.raises(TypeError) as exc_info:
        await dispatcher.invoke(
            InvokeMessage(
                id="req-broken",
                capability="plugin-alpha.broken",
                input={"available": "value"},
            ),
            CancelToken(),
        )

    message = str(exc_info.value)
    assert (
        "插件 'plugin-alpha' 的 capability 'plugin-alpha.broken' 参数注入失败"
        in message
    )
    assert "必填参数 'required_name' 无法注入" in message
    assert "payload 中现有键：available" in message


@pytest.mark.asyncio
async def test_registered_llm_tool_injects_event_and_normalizes_dict_result() -> None:
    peer = MockPeer(MockCapabilityRouter())

    async def tool_handler(
        event: MessageEvent,
        ctx: Context,
        text: str,
    ) -> dict[str, str]:
        return {
            "echo": text,
            "session": event.session_id,
            "plugin": ctx.plugin_id,
        }

    loaded_tool = LoadedLLMTool(
        spec=LLMToolSpec.create(
            name="echo",
            description="Echo",
            parameters_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
            handler_ref="echo.ref",
        ),
        callable=tool_handler,
        owner=object(),
        plugin_id="tool-plugin",
    )
    dispatcher = CapabilityDispatcher(
        plugin_id="worker-group",
        peer=peer,
        capabilities=[],
        llm_tools=[loaded_tool],
    )

    result = await dispatcher.invoke(
        InvokeMessage(
            id="req-tool",
            capability="internal.llm_tool.execute",
            input={
                "plugin_id": "tool-plugin",
                "tool_name": "echo",
                "handler_ref": "echo.ref",
                "tool_args": {"text": "hello"},
                "event": {
                    "type": "message",
                    "event_type": "message",
                    "text": "trigger",
                    "session_id": "session-42",
                    "user_id": "tester",
                    "platform": "test",
                    "platform_id": "test",
                    "message_type": "private",
                    "raw": {"event_type": "message"},
                },
            },
        ),
        CancelToken(),
    )

    assert result["success"] is True
    assert json.loads(str(result["content"])) == {
        "echo": "hello",
        "session": "session-42",
        "plugin": "tool-plugin",
    }


def test_dynamic_llm_tool_registration_replaces_aliases_and_remove_cleans_all_keys() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = CapabilityDispatcher(
        plugin_id="worker-group",
        peer=peer,
        capabilities=[],
    )

    async def first_tool() -> str:
        return "first"

    async def second_tool() -> str:
        return "second"

    dispatcher.add_dynamic_llm_tool(
        plugin_id="plugin.alpha",
        spec=LLMToolSpec.create(
            name="echo",
            description="Echo",
            handler_ref="echo.ref",
        ),
        callable_obj=first_tool,
    )
    dispatcher.add_dynamic_llm_tool(
        plugin_id="plugin.alpha",
        spec=LLMToolSpec.create(
            name="echo",
            description="Echo updated",
            handler_ref="echo.ref",
        ),
        callable_obj=second_tool,
    )

    loaded_by_name = dispatcher._llm_tools[("plugin.alpha", "echo")]
    loaded_by_ref = dispatcher._llm_tools[("plugin.alpha", "echo.ref")]

    assert loaded_by_name.callable is second_tool
    assert loaded_by_ref.callable is second_tool
    assert dispatcher.remove_llm_tool("plugin.alpha", "echo.ref") is True
    assert ("plugin.alpha", "echo") not in dispatcher._llm_tools
    assert ("plugin.alpha", "echo.ref") not in dispatcher._llm_tools


@pytest.mark.asyncio
async def test_capability_dispatcher_cancel_propagates_to_task_and_token() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = CapabilityDispatcher(
        plugin_id="worker-group",
        peer=peer,
        capabilities=[],
    )
    cancel_token = CancelToken()
    task = asyncio.create_task(asyncio.sleep(30))
    dispatcher._active["req-cancel"] = (task, cancel_token)

    await dispatcher.cancel("req-cancel")

    assert cancel_token.cancelled is True
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_capability_dispatcher_stream_mode_rejects_non_stream_result() -> None:
    peer = MockPeer(MockCapabilityRouter())

    async def non_stream_capability(payload: dict[str, Any]) -> dict[str, Any]:
        return {"payload": payload}

    dispatcher = CapabilityDispatcher(
        plugin_id="test-plugin",
        peer=peer,
        capabilities=[_build_loaded_capability(non_stream_capability)],
    )

    with pytest.raises(Exception, match="stream=true"):
        await dispatcher.invoke(
            InvokeMessage(
                id="req-stream-invalid",
                capability="test.echo",
                input={"name": "alice"},
                stream=True,
            ),
            CancelToken(),
        )
