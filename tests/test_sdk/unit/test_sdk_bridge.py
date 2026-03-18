# ruff: noqa: E402
from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace

import pytest

from astrbot_sdk.context import CancelToken
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    HandlerDescriptor,
    MessageTrigger,
    Permissions,
)
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import LoadedHandler
from astrbot_sdk.testing import MockCapabilityRouter, MockPeer

_TRIGGER_CONVERTER_SPEC = importlib.util.spec_from_file_location(
    "astrbot_sdk_bridge_trigger_converter_test",
    "d:\\GitObjectsOwn\\AstrBot\\astrbot\\core\\sdk_bridge\\trigger_converter.py",
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
