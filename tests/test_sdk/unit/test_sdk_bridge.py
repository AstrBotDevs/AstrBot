# ruff: noqa: E402
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot_sdk.clients.llm import LLMResponse
from astrbot_sdk.context import CancelToken
from astrbot_sdk.decorators import ConversationMeta
from astrbot_sdk.llm.entities import ProviderRequest
from astrbot_sdk.message_components import Plain
from astrbot_sdk.message_result import MessageEventResult
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    Permissions,
)
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import LoadedHandler
from astrbot_sdk.testing import MockCapabilityRouter, MockPeer

_TRIGGER_CONVERTER_SPEC = importlib.util.spec_from_file_location(
    "astrbot_sdk_bridge_trigger_converter_test",
    str(
        Path(__file__).resolve().parents[3]
        / "astrbot"
        / "core"
        / "sdk_bridge"
        / "trigger_converter.py"
    ),
)
assert _TRIGGER_CONVERTER_SPEC is not None
assert _TRIGGER_CONVERTER_SPEC.loader is not None
_TRIGGER_CONVERTER_MODULE = importlib.util.module_from_spec(_TRIGGER_CONVERTER_SPEC)
sys.modules.setdefault(
    "astrbot_sdk_bridge_trigger_converter_test",
    _TRIGGER_CONVERTER_MODULE,
)
_TRIGGER_CONVERTER_SPEC.loader.exec_module(_TRIGGER_CONVERTER_MODULE)
TriggerConverter = _TRIGGER_CONVERTER_MODULE.TriggerConverter


class _FakeEvent:
    def __init__(
        self,
        *,
        text: str,
        platform: str = "test",
        message_type: str = "private",
        admin: bool = False,
    ) -> None:
        self._text = text
        self._platform = platform
        self._message_type = message_type
        self._admin = admin
        self._group_id = "group-1" if message_type == "group" else ""
        self._sender_id = "user-1"
        self._has_send_oper = False

    def get_message_type(self):
        return SimpleNamespace(value=self._message_type)

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_platform_name(self) -> str:
        return self._platform

    def get_message_str(self) -> str:
        return self._text

    def is_admin(self) -> bool:
        return self._admin


class _CommandPlugin:
    async def echo(self, phrase: str):
        return {"text": phrase, "stop": True}


class _RegexPlugin:
    async def capture(self, word: str):
        return {"text": word}


class _ConversationPlugin:
    def __init__(self) -> None:
        self.started = False

    async def chat(self, event, conversation, ctx):
        self.started = True
        conversation.end()


class _LLMRequestHookPlugin:
    async def decorate(self, request: ProviderRequest) -> None:
        request.system_prompt = "decorated memory prompt"
        request.contexts.append({"role": "system", "content": "memory: user likes tea"})


class _LLMResponseHookPlugin:
    async def inspect(self, response: LLMResponse) -> dict[str, object]:
        return {
            "text": response.text,
            "llm_response": response.model_dump(exclude_none=True),
        }


class _DecoratingResultHookPlugin:
    async def decorate(self, result: MessageEventResult) -> None:
        result.chain.append(Plain(" decorated", convert=False))


@pytest.mark.unit
def test_trigger_converter_matches_command_and_respects_admin() -> None:
    descriptor = HandlerDescriptor(
        id="demo:demo.echo",
        trigger=CommandTrigger(command="ping"),
        priority=5,
        permissions=Permissions(require_admin=True),
    )

    assert (
        TriggerConverter.match_handler(
            plugin_id="demo",
            descriptor=descriptor,
            event=_FakeEvent(text="ping hello", admin=False),
            load_order=0,
            declaration_order=0,
        )
        is None
    )

    match = TriggerConverter.match_handler(
        plugin_id="demo",
        descriptor=descriptor,
        event=_FakeEvent(text="ping hello", admin=True),
        load_order=0,
        declaration_order=0,
    )
    assert match is not None
    assert match.plugin_id == "demo"
    assert match.handler_id == "demo:demo.echo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_dispatcher_derives_command_args_and_returns_summary() -> None:
    plugin = _CommandPlugin()
    router = MockCapabilityRouter()
    peer = MockPeer(router)
    dispatcher = HandlerDispatcher(
        plugin_id="demo",
        peer=peer,
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="demo:demo.echo",
                    trigger=CommandTrigger(command="ping"),
                ),
                callable=plugin.echo,
                owner=plugin,
                plugin_id="demo",
            )
        ],
    )

    result = await dispatcher.invoke(
        SimpleNamespace(
            id="req-1",
            input={
                "handler_id": "demo:demo.echo",
                "event": {
                    "text": "ping hello world",
                    "session_id": "test-session",
                    "user_id": "test-user",
                    "platform": "test",
                    "message_type": "private",
                },
            },
        ),
        CancelToken(),
    )

    assert result == {"sent_message": True, "stop": True, "call_llm": False}
    assert router.platform_sink.records[0].text == "hello world"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_dispatcher_derives_regex_args() -> None:
    plugin = _RegexPlugin()
    router = MockCapabilityRouter()
    peer = MockPeer(router)
    dispatcher = HandlerDispatcher(
        plugin_id="demo",
        peer=peer,
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="demo:demo.capture",
                    trigger=MessageTrigger(regex=r"hello (?P<word>\w+)"),
                ),
                callable=plugin.capture,
                owner=plugin,
                plugin_id="demo",
            )
        ],
    )

    result = await dispatcher.invoke(
        SimpleNamespace(
            id="req-2",
            input={
                "handler_id": "demo:demo.capture",
                "event": {
                    "text": "hello sdk",
                    "session_id": "test-session",
                    "user_id": "test-user",
                    "platform": "test",
                    "message_type": "private",
                },
            },
        ),
        CancelToken(),
    )

    assert result == {"sent_message": True, "stop": False, "call_llm": False}
    assert router.platform_sink.records[0].text == "sdk"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_command_consumes_trigger_message() -> None:
    plugin = _ConversationPlugin()
    router = MockCapabilityRouter()
    peer = MockPeer(router)
    dispatcher = HandlerDispatcher(
        plugin_id="demo",
        peer=peer,
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="demo:demo.chat",
                    trigger=CommandTrigger(command="chat"),
                ),
                callable=plugin.chat,
                owner=plugin,
                plugin_id="demo",
                conversation=ConversationMeta(timeout=60, mode="replace"),
            )
        ],
    )

    result = await dispatcher.invoke(
        SimpleNamespace(
            id="req-3",
            input={
                "handler_id": "demo:demo.chat",
                "event": {
                    "text": "chat",
                    "session_id": "test-session",
                    "user_id": "test-user",
                    "platform": "test",
                    "message_type": "private",
                },
            },
        ),
        CancelToken(),
    )
    await asyncio.sleep(0)

    assert result == {"sent_message": False, "stop": True, "call_llm": False}
    assert plugin.started is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_dispatcher_injects_and_round_trips_provider_request() -> None:
    plugin = _LLMRequestHookPlugin()
    dispatcher = HandlerDispatcher(
        plugin_id="demo",
        peer=MockPeer(MockCapabilityRouter()),
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="demo:demo.decorate",
                    trigger=EventTrigger(event_type="llm_request"),
                ),
                callable=plugin.decorate,
                owner=plugin,
                plugin_id="demo",
            )
        ],
    )

    result = await dispatcher.invoke(
        SimpleNamespace(
            id="req-4",
            input={
                "handler_id": "demo:demo.decorate",
                "event": {
                    "type": "llm_request",
                    "event_type": "llm_request",
                    "text": "hello",
                    "session_id": "test-session",
                    "user_id": "test-user",
                    "platform": "test",
                    "message_type": "private",
                    "provider_request": {
                        "prompt": "hello",
                        "system_prompt": "original",
                        "contexts": [],
                        "image_urls": [],
                        "tool_calls_result": [],
                    },
                },
            },
        ),
        CancelToken(),
    )

    assert result["sent_message"] is False
    assert result["stop"] is False
    assert result["call_llm"] is False
    assert result["provider_request"]["system_prompt"] == "decorated memory prompt"
    assert result["provider_request"]["contexts"][-1] == {
        "role": "system",
        "content": "memory: user likes tea",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_dispatcher_injects_llm_response_payload() -> None:
    plugin = _LLMResponseHookPlugin()
    router = MockCapabilityRouter()
    dispatcher = HandlerDispatcher(
        plugin_id="demo",
        peer=MockPeer(router),
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="demo:demo.inspect",
                    trigger=EventTrigger(event_type="llm_response"),
                ),
                callable=plugin.inspect,
                owner=plugin,
                plugin_id="demo",
            )
        ],
    )

    result = await dispatcher.invoke(
        SimpleNamespace(
            id="req-5",
            input={
                "handler_id": "demo:demo.inspect",
                "event": {
                    "type": "llm_response",
                    "event_type": "llm_response",
                    "text": "hello",
                    "session_id": "test-session",
                    "user_id": "test-user",
                    "platform": "test",
                    "message_type": "private",
                    "llm_response": {
                        "text": "reply text",
                        "usage": {"total_tokens": 3},
                        "finish_reason": "stop",
                        "tool_calls": [],
                        "role": "assistant",
                    },
                },
            },
        ),
        CancelToken(),
    )

    assert result["sent_message"] is True
    assert router.platform_sink.records[0].text == "reply text"
    assert result["llm_response"]["text"] == "reply text"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_dispatcher_injects_and_round_trips_event_result() -> None:
    plugin = _DecoratingResultHookPlugin()
    dispatcher = HandlerDispatcher(
        plugin_id="demo",
        peer=MockPeer(MockCapabilityRouter()),
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="demo:demo.decorate_result",
                    trigger=EventTrigger(event_type="decorating_result"),
                ),
                callable=plugin.decorate,
                owner=plugin,
                plugin_id="demo",
            )
        ],
    )

    result = await dispatcher.invoke(
        SimpleNamespace(
            id="req-6",
            input={
                "handler_id": "demo:demo.decorate_result",
                "event": {
                    "type": "decorating_result",
                    "event_type": "decorating_result",
                    "text": "hello",
                    "session_id": "test-session",
                    "user_id": "test-user",
                    "platform": "test",
                    "message_type": "private",
                    "event_result": {
                        "type": "chain",
                        "chain": [{"type": "plain", "data": {"text": "base"}}],
                    },
                },
            },
        ),
        CancelToken(),
    )

    assert result["event_result"]["chain"][0]["data"]["text"] == "base"
    assert result["event_result"]["chain"][1]["data"]["text"] == " decorated"
