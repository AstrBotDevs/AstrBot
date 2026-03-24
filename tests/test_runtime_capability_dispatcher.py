from __future__ import annotations

import json
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
