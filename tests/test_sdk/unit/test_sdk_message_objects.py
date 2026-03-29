# ruff: noqa: E402, I001
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot.core.message.components import File as CoreFile
from astrbot.core.message.components import Plain as CorePlain
from astrbot.core.message.components import Reply as CoreReply
from astrbot.core.sdk_bridge.event_payload import (
    build_inbound_event_snapshot,
    sanitize_sdk_extras,
)
from astrbot_sdk import MessageEvent
from astrbot_sdk import message_components as sdk_message_components
from astrbot_sdk._plugin_logger import PluginLogEntry
from astrbot_sdk._star_runtime import bind_star_runtime
from astrbot_sdk.context import Context
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.message_components import (
    File,
    Image,
    Plain,
    Reply,
    UnknownComponent,
    component_to_payload,
    payloads_to_components,
)
from astrbot_sdk.message_result import EventResultType, MessageChain, MessageEventResult
from astrbot_sdk.protocol.descriptors import SessionRef
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher


class _DummyPeer:
    def __init__(self) -> None:
        self.remote_peer = {"name": "dummy-core"}
        self.remote_capability_map = {
            "platform.send": SimpleNamespace(supports_stream=False),
            "platform.send_chain": SimpleNamespace(supports_stream=False),
            "platform.send_by_session": SimpleNamespace(supports_stream=False),
            "platform.get_group": SimpleNamespace(supports_stream=False),
            "platform.list_instances": SimpleNamespace(supports_stream=False),
            "registry.command.register": SimpleNamespace(supports_stream=False),
            "system.event.react": SimpleNamespace(supports_stream=False),
            "system.event.send_typing": SimpleNamespace(supports_stream=False),
            "system.event.send_streaming": SimpleNamespace(supports_stream=False),
            "system.event.send_streaming_chunk": SimpleNamespace(supports_stream=False),
            "system.event.send_streaming_close": SimpleNamespace(supports_stream=False),
            "system.file.register": SimpleNamespace(supports_stream=False),
            "system.file.handle": SimpleNamespace(supports_stream=False),
        }
        self.sent_messages: list[dict] = []
        self.event_actions: list[dict] = []
        self.command_registrations: list[dict] = []
        self.platform_instances = [
            {
                "id": "demo",
                "name": "Demo Platform",
                "type": "demo",
                "status": "running",
            }
        ]
        self._open_streams: dict[str, dict] = {}
        self._file_tokens: dict[str, str] = {}

    async def invoke(self, capability: str, payload: dict, *, stream: bool = False):
        if stream:
            raise ValueError("stream unsupported in dummy peer")
        if capability == "platform.send":
            self.sent_messages.append(
                {
                    "kind": "text",
                    "session": payload.get("session"),
                    "text": payload.get("text"),
                }
            )
            return {"message_id": "text-1"}
        if capability == "platform.send_chain":
            self.sent_messages.append(
                {
                    "kind": "chain",
                    "session": payload.get("session"),
                    "chain": payload.get("chain"),
                }
            )
            return {"message_id": "chain-1"}
        if capability == "platform.send_by_session":
            self.sent_messages.append(
                {
                    "kind": "chain",
                    "session": payload.get("session"),
                    "chain": payload.get("chain"),
                }
            )
            return {"message_id": "proactive-1"}
        if capability == "platform.get_group":
            session = str(payload.get("session", ""))
            if ":group:" not in session:
                return {"group": None}
            return {
                "group": {
                    "group_id": "room-7",
                    "group_name": "Room 7",
                    "group_avatar": "",
                    "group_owner": "owner-1",
                    "group_admins": ["admin-1"],
                    "members": [
                        {
                            "user_id": "member-1",
                            "nickname": "Member 1",
                            "role": "member",
                        }
                    ],
                }
            }
        if capability == "platform.list_instances":
            return {"platforms": list(self.platform_instances)}
        if capability == "registry.command.register":
            self.command_registrations.append(dict(payload))
            return {}
        if capability == "system.event.react":
            self.event_actions.append(
                {"action": "react", "emoji": payload.get("emoji")}
            )
            return {"supported": True}
        if capability == "system.event.send_typing":
            self.event_actions.append({"action": "send_typing"})
            return {"supported": True}
        if capability == "system.event.send_streaming":
            stream_id = f"stream-{len(self._open_streams) + 1}"
            self._open_streams[stream_id] = {
                "chunks": [],
                "use_fallback": payload.get("use_fallback"),
            }
            return {"supported": True, "stream_id": stream_id}
        if capability == "system.event.send_streaming_chunk":
            stream_id = str(payload.get("stream_id"))
            self._open_streams[stream_id]["chunks"].append(
                {"chain": payload.get("chain")}
            )
            return {}
        if capability == "system.event.send_streaming_close":
            stream_id = str(payload.get("stream_id"))
            stream = self._open_streams.pop(stream_id)
            self.event_actions.append(
                {
                    "action": "send_streaming",
                    "chunks": stream["chunks"],
                    "use_fallback": stream["use_fallback"],
                }
            )
            return {"supported": True}
        if capability == "system.file.register":
            token = f"file-{len(self._file_tokens) + 1}"
            self._file_tokens[token] = str(payload.get("path", ""))
            return {
                "token": token,
                "url": f"https://callback.example/api/file/{token}",
            }
        if capability == "system.file.handle":
            token = str(payload.get("token", ""))
            path = self._file_tokens.pop(token)
            return {"path": path}
        raise AssertionError(f"unexpected capability: {capability}")

    async def invoke_stream(self, capability: str, payload: dict):
        raise AssertionError(f"unexpected stream capability: {capability}")


@pytest.mark.unit
def test_payload_to_components_and_event_local_state() -> None:
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:private:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "private",
            "message_outline": "hello [UnknownComponent]",
            "sent_message_outline": "assistant reply",
            "messages": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "mystery", "data": {"payload": 1}},
            ],
            "sent_messages": [
                {"type": "text", "data": {"text": "assistant reply"}},
            ],
            "extras": {"seed": "value", "local": "seed"},
            "host_extras": {"seed": "value"},
            "sdk_local_extras": {"local": "seed"},
        }
    )

    messages = event.get_messages()
    sent_messages = event.get_sent_messages()
    assert len(messages) == 2
    assert isinstance(messages[0], Plain)
    assert isinstance(messages[1], UnknownComponent)
    assert len(sent_messages) == 1
    assert isinstance(sent_messages[0], Plain)
    assert event.get_message_outline() == "hello [UnknownComponent]"
    assert event.get_sent_message_outline() == "assistant reply"
    assert event.get_extra("seed") == "value"
    assert event.get_extra("local") == "seed"

    event.set_extra("local", 42)
    assert event.get_extra("local") == 42
    assert event.get_extra()["local"] == 42
    event.clear_extra()
    assert event.get_extra("local", "missing") == "missing"

    empty_result = event.make_result()
    assert empty_result.type is EventResultType.EMPTY
    assert empty_result.chain.components == []

    image_result = event.image_result("https://example.com/a.png")
    assert image_result.type is EventResultType.CHAIN
    assert isinstance(image_result.chain.components[0], Image)

    chain_result = event.chain_result([Plain("sdk", convert=False)])
    assert chain_result.type is EventResultType.CHAIN
    assert chain_result.chain.get_plain_text() == "sdk"


@pytest.mark.unit
def test_message_event_normalizes_legacy_core_message_types() -> None:
    private_event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:FriendMessage:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "FriendMessage",
        }
    )
    group_event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:GroupMessage:room-1",
            "platform": "demo",
            "platform_id": "demo",
            "group_id": "room-1",
            "message_type": "GroupMessage",
        }
    )

    assert private_event.get_message_type() == "private"
    assert private_event.is_private_chat() is True
    assert group_event.get_message_type() == "group"
    assert group_event.is_group_chat() is True


@pytest.mark.unit
def test_message_event_to_payload_drops_non_serializable_sdk_local_extras() -> None:
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:private:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "private",
            "extras": {"seed": "value"},
            "host_extras": {"seed": "value"},
            "sdk_local_extras": {},
        }
    )

    event.set_extra("persisted", "ok")
    event.set_extra("bad", object())

    payload = event.to_payload()

    assert payload["extras"] == {"seed": "value", "persisted": "ok"}
    assert payload["sdk_local_extras"] == {"persisted": "ok"}
    assert "bad" not in payload["sdk_local_extras"]


@pytest.mark.unit
def test_payloads_to_components_unknown_fallback() -> None:
    components = payloads_to_components(
        [
            {"type": "text", "data": {"text": "hi"}},
            {"type": "unknown-segment", "data": {"foo": "bar"}},
        ]
    )

    assert isinstance(components[0], Plain)
    assert isinstance(components[1], UnknownComponent)
    assert components[1].toDict() == {
        "type": "unknown-segment",
        "data": {"foo": "bar"},
    }


@pytest.mark.unit
def test_reply_component_roundtrip_keeps_chain_and_metadata() -> None:
    payload = {
        "type": "reply",
        "data": {
            "id": "reply-1",
            "sender_id": "user-9",
            "sender_nickname": "Tester",
            "message_str": "quoted text",
            "chain": [{"type": "text", "data": {"text": "quoted text"}}],
        },
    }

    component = sdk_message_components.payload_to_component(payload)

    assert isinstance(component, sdk_message_components.Reply)
    assert component.sender_id == "user-9"
    assert component.message_str == "quoted text"
    assert len(component.chain) == 1
    assert isinstance(component.chain[0], Plain)
    normalized = sdk_message_components.component_to_payload_sync(component)
    assert normalized["type"] == "reply"
    assert normalized["data"]["id"] == "reply-1"
    assert normalized["data"]["sender_id"] == "user-9"
    assert normalized["data"]["sender_nickname"] == "Tester"
    assert normalized["data"]["message_str"] == "quoted text"
    assert normalized["data"]["chain"] == payload["data"]["chain"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_plain_component_payload_paths_are_consistent() -> None:
    component = Plain("  keep spacing  ", convert=False)

    assert component.toDict() == {
        "type": "text",
        "data": {"text": "  keep spacing  "},
    }
    assert await component.to_dict() == component.toDict()
    assert (
        sdk_message_components.component_to_payload_sync(component)
        == component.toDict()
    )
    assert await component_to_payload(component) == component.toDict()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_reply_component_payload_paths_are_consistent() -> None:
    component = Reply(
        id="reply-1",
        sender_id="user-9",
        sender_nickname="Tester",
        message_str="quoted text",
        chain=[Plain("quoted text", convert=False)],
    )

    expected = {
        "type": "reply",
        "data": {
            "id": "reply-1",
            "chain": [{"type": "text", "data": {"text": "quoted text"}}],
            "sender_id": "user-9",
            "sender_nickname": "Tester",
            "time": 0,
            "message_str": "quoted text",
            "text": "",
            "qq": 0,
            "seq": 0,
        },
    }

    assert component.toDict() == expected
    assert await component.to_dict() == expected
    assert sdk_message_components.component_to_payload_sync(component) == expected
    assert await component_to_payload(component) == expected


def _build_sdk_payload_from_core_event(event) -> dict[str, object]:
    return build_inbound_event_snapshot(event).to_payload(
        dispatch_token="dispatch-1",
        plugin_id="sdk-demo",
        request_id="req-1",
        host_extras=sanitize_sdk_extras(event.get_extra()),
        sdk_local_extras={},
    )


@pytest.mark.unit
def test_inbound_snapshot_serializes_core_reply_chain() -> None:
    reply = CoreReply(
        id="reply-2",
        sender_id="user-8",
        sender_nickname="Quoted",
        message_str="quoted core text",
        chain=[CorePlain(text="quoted core text")],
    )

    class _CoreEvent:
        is_wake = False
        is_at_or_wake_command = False

        def get_message_type(self):
            return SimpleNamespace(value="private")

        def get_message_str(self) -> str:
            return "hello"

        def get_sender_id(self) -> str:
            return "user-1"

        def get_group_id(self) -> str:
            return ""

        def get_platform_name(self) -> str:
            return "demo"

        def get_platform_id(self) -> str:
            return "demo"

        def get_self_id(self) -> str:
            return "bot-1"

        def get_sender_name(self) -> str:
            return "Sender"

        def is_admin(self) -> bool:
            return False

        def get_message_outline(self) -> str:
            return "hello"

        def get_extra(self) -> dict[str, object]:
            return {}

        @property
        def unified_msg_origin(self) -> str:
            return "demo:private:user-1"

        def get_messages(self):
            return [reply]

    payload = _build_sdk_payload_from_core_event(_CoreEvent())

    reply_payload = payload["messages"][0]
    assert reply_payload["type"] == "reply"
    assert reply_payload["data"]["sender_id"] == "user-8"
    assert reply_payload["data"]["message_str"] == "quoted core text"
    assert reply_payload["data"]["chain"] == [
        {"type": "text", "data": {"text": "quoted core text"}}
    ]


@pytest.mark.unit
def test_inbound_snapshot_normalizes_legacy_core_message_type_values() -> None:
    class _LegacyCoreEvent:
        is_wake = False
        is_at_or_wake_command = False

        def get_message_type(self):
            return SimpleNamespace(value="FriendMessage")

        def get_message_str(self) -> str:
            return "hello"

        def get_sender_id(self) -> str:
            return "user-1"

        def get_group_id(self) -> str:
            return ""

        def get_platform_name(self) -> str:
            return "demo"

        def get_platform_id(self) -> str:
            return "demo"

        def get_self_id(self) -> str:
            return "bot-1"

        def get_sender_name(self) -> str:
            return "Sender"

        def is_admin(self) -> bool:
            return False

        def get_message_outline(self) -> str:
            return "hello"

        def get_extra(self, key: str | None = None, default=None):
            del key, default
            return {}

        @property
        def unified_msg_origin(self) -> str:
            return "demo:FriendMessage:user-1"

        def get_messages(self):
            return [CorePlain(text="hello")]

    payload = _build_sdk_payload_from_core_event(_LegacyCoreEvent())

    assert payload["message_type"] == "private"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("group_id", "sender_id", "expected"),
    [
        ("group-1", "user-1", "group"),
        ("", "user-1", "private"),
        ("", "", "other"),
    ],
)
def test_event_converter_message_type_falls_back_to_event_shape(
    group_id: str,
    sender_id: str,
    expected: str,
) -> None:
    class _UnknownTypeEvent:
        is_wake = False
        is_at_or_wake_command = False

        def get_message_type(self):
            return SimpleNamespace(value="channel")

        def get_message_str(self) -> str:
            return "hello"

        def get_sender_id(self) -> str:
            return sender_id

        def get_group_id(self) -> str:
            return group_id

        def get_platform_name(self) -> str:
            return "demo"

        def get_platform_id(self) -> str:
            return "demo"

        def get_self_id(self) -> str:
            return "bot-1"

        def get_sender_name(self) -> str:
            return "Sender"

        def is_admin(self) -> bool:
            return False

        def get_message_outline(self) -> str:
            return "hello"

        def get_extra(self, key: str | None = None, default=None):
            del key, default
            return {}

        @property
        def unified_msg_origin(self) -> str:
            return "demo:channel:user-1"

        def get_messages(self):
            return [CorePlain(text="hello")]

    payload = _build_sdk_payload_from_core_event(_UnknownTypeEvent())

    assert payload["message_type"] == expected


@pytest.mark.unit
def test_file_component_roundtrip_accepts_legacy_core_payload() -> None:
    payload = sdk_message_components.component_to_payload_sync(
        CoreFile(name="sample.txt", file="C:/tmp/sample.txt")
    )

    component = sdk_message_components.payload_to_component(payload)

    assert isinstance(component, File)
    assert component.file == "C:/tmp/sample.txt"
    assert component.toDict() == {
        "type": "file",
        "data": {"name": "sample.txt", "file": "C:/tmp/sample.txt"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_component_file_methods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")

    image = Image.fromFileSystem(str(sample))
    assert await image.convert_to_file_path() == str(sample.resolve())

    file_component = File(name="sample.txt", file=str(sample))
    assert await file_component.get_file() == str(sample.resolve())

    async def fake_register_file_to_service(path: str) -> str:
        assert path == str(sample.resolve())
        return "https://callback.example/api/file/token-123"

    monkeypatch.setattr(
        sdk_message_components,
        "_register_file_to_service",
        fake_register_file_to_service,
    )

    assert (
        await image.register_to_file_service()
        == "https://callback.example/api/file/token-123"
    )
    assert (
        await file_component.register_to_file_service()
        == "https://callback.example/api/file/token-123"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_component_file_service_requires_runtime_context(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    image = Image.fromFileSystem(str(sample))

    with pytest.raises(RuntimeError, match="runtime context"):
        await image.register_to_file_service()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_component_file_service_uses_current_runtime_context(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    image = Image.fromFileSystem(str(sample))
    ctx = Context(peer=_DummyPeer(), plugin_id="sdk-demo")

    with bind_star_runtime(None, ctx):
        url = await image.register_to_file_service()

    assert url == "https://callback.example/api/file/file-1"
    token = await ctx.files.register_file(str(sample))
    assert token == "file-2"
    assert await ctx.files.handle_file(token) == str(sample)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_event_actions_and_send_chain_with_mock_context() -> None:
    peer = _DummyPeer()
    ctx = Context(peer=peer, plugin_id="sdk-demo")
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:private:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "private",
            "target": SessionRef(conversation_id="demo:private:user-1").to_payload(),
        },
        context=ctx,
    )

    assert await event.react("👍") is True
    assert await event.send_typing() is True

    async def generator():
        yield "sdk"
        yield [Plain(" stream", convert=False)]

    assert await event.send_streaming(generator(), use_fallback=True) is True

    await ctx.platform.send_chain(event.session_id, MessageChain([Plain("chain")]))

    assert [item["action"] for item in peer.event_actions] == [
        "react",
        "send_typing",
        "send_streaming",
    ]
    assert peer.event_actions[-1]["chunks"] == [
        {"chain": [{"type": "text", "data": {"text": "sdk"}}]},
        {"chain": [{"type": "text", "data": {"text": " stream"}}]},
    ]
    assert peer.sent_messages[-1]["kind"] == "chain"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_platform_send_by_session_accepts_existing_payload_shapes() -> None:
    peer = _DummyPeer()
    ctx = Context(peer=peer, plugin_id="sdk-demo")

    await ctx.platform.send_by_session(
        "demo:private:user-2",
        [{"type": "text", "data": {"text": "dict-payload"}}],
    )
    await ctx.platform.send_by_session(
        "demo:private:user-3",
        MessageChain([Plain("message-chain", convert=False)]),
    )
    await ctx.platform.send_by_session(
        "demo:private:user-4",
        [Plain("component-list", convert=False)],
    )
    await ctx.platform.send_by_id("demo", "user-5", "plain-text")

    assert peer.sent_messages[0] == {
        "kind": "chain",
        "session": "demo:private:user-2",
        "chain": [{"type": "text", "data": {"text": "dict-payload"}}],
    }
    assert peer.sent_messages[1]["chain"] == [
        {"type": "text", "data": {"text": "message-chain"}}
    ]
    assert peer.sent_messages[2]["chain"] == [
        {"type": "text", "data": {"text": "component-list"}}
    ]
    assert peer.sent_messages[3] == {
        "kind": "chain",
        "session": "demo:private:user-5",
        "chain": [{"type": "text", "data": {"text": "plain-text"}}],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_p0_7_register_commands_and_platform_facade() -> None:
    peer = _DummyPeer()
    peer.platform_instances = [
        {
            "id": "demo",
            "name": "Demo Platform",
            "type": "demo",
            "status": "running",
        },
        {
            "id": "demo-2",
            "name": "Demo Platform 2",
            "type": "demo",
            "status": "stopped",
        },
        {
            "id": "",
            "name": "Broken Platform",
            "type": "broken",
            "status": "running",
        },
    ]
    ctx = Context(
        peer=peer,
        plugin_id="sdk-demo",
        source_event_payload={"event_type": "astrbot_loaded"},
    )

    await ctx.register_commands(
        "hello",
        "sdk-demo:demo.handler",
        desc="demo command",
        priority=7,
        use_regex=False,
    )
    platforms = await ctx.list_platforms()
    platform = await ctx.get_platform("demo")
    assert platform is not None
    assert platform.id == "demo"
    assert platform.status == "running"
    assert await ctx.get_platform_inst("missing") is None
    assert [item.id for item in platforms] == ["demo", "demo-2"]
    assert [item.status for item in platforms] == ["running", "stopped"]

    await platform.send_by_id("user-99", "hello from facade")

    assert peer.command_registrations == [
        {
            "command_name": "hello",
            "handler_full_name": "sdk-demo:demo.handler",
            "source_event_type": "astrbot_loaded",
            "desc": "demo command",
            "priority": 7,
            "use_regex": False,
            "ignore_prefix": False,
        }
    ]
    assert peer.sent_messages[-1]["session"] == "demo:private:user-99"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_commands_requires_startup_event() -> None:
    peer = _DummyPeer()
    ctx = Context(peer=peer, plugin_id="sdk-demo")

    with pytest.raises(AstrBotError, match="astrbot_loaded/platform_loaded"):
        await ctx.register_commands("hello", "sdk-demo:demo.handler")

    with pytest.raises(AstrBotError, match="ignore_prefix=True"):
        startup_ctx = Context(
            peer=peer,
            plugin_id="sdk-demo",
            source_event_payload={"type": "platform_loaded"},
        )
        await startup_ctx.register_commands(
            "hello",
            "sdk-demo:demo.handler",
            ignore_prefix=True,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_commands_rejects_bool_priority() -> None:
    peer = _DummyPeer()
    ctx = Context(
        peer=peer,
        plugin_id="sdk-demo",
        source_event_payload={"event_type": "astrbot_loaded"},
    )

    with pytest.raises(AstrBotError, match="priority must be an integer"):
        await ctx.register_commands(
            "hello",
            "sdk-demo:demo.handler",
            priority=True,
        )

    assert peer.command_registrations == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_task_logs_background_exceptions() -> None:
    class _ProbeLogger:
        def __init__(self) -> None:
            self.exception_calls: list[
                tuple[tuple[object, ...], dict[str, object]]
            ] = []
            self.debug_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def exception(self, *args, **kwargs) -> None:
            self.exception_calls.append((args, kwargs))

        def debug(self, *args, **kwargs) -> None:
            self.debug_calls.append((args, kwargs))

    async def _boom() -> None:
        raise RuntimeError("boom")

    logger = _ProbeLogger()
    ctx = Context(peer=_DummyPeer(), plugin_id="sdk-demo", logger=logger)
    task = await ctx.register_task(_boom(), "probe-task")

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert task.done() is True
    assert len(logger.exception_calls) == 1
    msg, plugin_id, desc, error = logger.exception_calls[0][0]
    assert "background task failed" in str(msg).lower()
    assert plugin_id == "sdk-demo"
    assert desc == "probe-task"
    assert error == "boom"
    assert logger.debug_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_commands_wraps_bridge_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = Context(
        peer=_DummyPeer(),
        plugin_id="sdk-demo",
        source_event_payload={"event_type": "astrbot_loaded"},
    )

    async def _boom(_capability: str, _payload: dict[str, object]) -> dict[str, object]:
        raise AstrBotError.invalid_input("bridge rejected")

    monkeypatch.setattr(ctx._proxy, "call", _boom)  # noqa: SLF001

    with pytest.raises(AstrBotError) as exc_info:
        await ctx.register_commands("hello", "sdk-demo:demo.handler")

    assert exc_info.value.code == "invalid_input"
    assert "Context.register_commands (" in str(exc_info.value)
    assert "command_name='hello'" in str(exc_info.value)
    assert "handler_full_name='sdk-demo:demo.handler'" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_skill_wraps_client_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = Context(peer=_DummyPeer(), plugin_id="sdk-demo")
    skill_dir = tmp_path / "writer_helper"

    async def _boom(**_kwargs):
        raise ValueError("missing SKILL.md")

    monkeypatch.setattr(ctx.skills, "register", _boom)

    with pytest.raises(RuntimeError, match="Context.register_skill") as exc_info:
        await ctx.register_skill(name="sdk-demo.writer-helper", path=skill_dir)

    assert "name='sdk-demo.writer-helper'" in str(exc_info.value)
    assert "path='" in str(exc_info.value)
    assert "writer_helper" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_llm_tool_wraps_errors_and_cleans_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Dispatcher:
        def __init__(self) -> None:
            self.add_calls: list[tuple[str, str]] = []
            self.remove_calls: list[tuple[str, str]] = []

        def add_dynamic_llm_tool(self, *, plugin_id, spec, callable_obj, owner) -> None:
            del callable_obj, owner
            self.add_calls.append((plugin_id, spec.name))

        def remove_llm_tool(self, plugin_id: str, tool_name: str) -> None:
            self.remove_calls.append((plugin_id, tool_name))

    peer = _DummyPeer()
    dispatcher = _Dispatcher()
    peer._sdk_capability_dispatcher = dispatcher  # type: ignore[attr-defined]
    ctx = Context(peer=peer, plugin_id="sdk-demo")

    async def _boom(*_tools):
        raise ValueError("tool registry down")

    monkeypatch.setattr(ctx._llm_tool_manager, "add", _boom)  # noqa: SLF001

    async def _tool() -> dict[str, bool]:
        return {"ok": True}

    with pytest.raises(RuntimeError, match="Context.register_llm_tool") as exc_info:
        await ctx.register_llm_tool(
            "demo-tool",
            {"type": "object"},
            "demo",
            _tool,
        )

    assert "name='demo-tool'" in str(exc_info.value)
    assert dispatcher.add_calls == [("sdk-demo", "demo-tool")]
    assert dispatcher.remove_calls == [("sdk-demo", "demo-tool")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_list_platforms_wraps_proxy_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = Context(peer=_DummyPeer(), plugin_id="sdk-demo")

    async def _boom(_capability: str, _payload: dict[str, object]) -> dict[str, object]:
        raise AstrBotError.invalid_input("platform backend unavailable")

    monkeypatch.setattr(ctx._proxy, "call", _boom)  # noqa: SLF001

    with pytest.raises(AstrBotError) as exc_info:
        await ctx.list_platforms()

    assert exc_info.value.code == "invalid_input"
    assert "Context.list_platforms failed" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_register_task_rejects_non_awaitable_with_desc() -> None:
    ctx = Context(peer=_DummyPeer(), plugin_id="sdk-demo")

    with pytest.raises(TypeError, match="Context.register_task requires an awaitable"):
        await ctx.register_task(123, "probe-task")  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_logger_watch_streams_current_plugin_logs() -> None:
    ctx = Context(peer=_DummyPeer(), plugin_id="sdk-demo")
    watcher = ctx.logger.watch()

    async def _next_entry() -> PluginLogEntry:
        return await watcher.__anext__()

    pending = asyncio.create_task(_next_entry())
    await asyncio.sleep(0)
    ctx.logger.info("hello {}", "sdk")
    entry = await pending

    assert entry.plugin_id == "sdk-demo"
    assert entry.level == "INFO"
    assert entry.message == "hello sdk"

    await watcher.aclose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_event_get_group_returns_group_only_for_group_session() -> None:
    peer = _DummyPeer()
    ctx = Context(peer=peer, plugin_id="sdk-demo")
    group_event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:group:room-7",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "group",
            "target": SessionRef(conversation_id="demo:group:room-7").to_payload(),
        },
        context=ctx,
    )
    private_event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:private:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "private",
            "target": SessionRef(conversation_id="demo:private:user-1").to_payload(),
        },
        context=ctx,
    )

    group = await group_event.get_group()
    private_group = await private_event.get_group()

    assert group is not None
    assert group["group_id"] == "room-7"
    assert private_group is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_streaming_pushes_chunks_incrementally() -> None:
    peer = _DummyPeer()
    ctx = Context(peer=peer, plugin_id="sdk-demo")
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:private:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "private",
            "target": SessionRef(conversation_id="demo:private:user-1").to_payload(),
        },
        context=ctx,
    )

    async def generator():
        yield "sdk"
        assert peer._open_streams["stream-1"]["chunks"] == [
            {"chain": [{"type": "text", "data": {"text": "sdk"}}]}
        ]
        yield [Plain(" stream", convert=False)]

    assert await event.send_streaming(generator(), use_fallback=True) is True
    assert peer.event_actions[-1]["chunks"] == [
        {"chain": [{"type": "text", "data": {"text": "sdk"}}]},
        {"chain": [{"type": "text", "data": {"text": " stream"}}]},
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_dispatcher_normalizes_sdk_result_objects() -> None:
    dispatcher = HandlerDispatcher.__new__(HandlerDispatcher)
    peer = _DummyPeer()
    ctx = Context(peer=peer, plugin_id="sdk-demo")
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "demo:private:user-1",
            "platform": "demo",
            "platform_id": "demo",
            "message_type": "private",
            "target": SessionRef(conversation_id="demo:private:user-1").to_payload(),
        },
        context=ctx,
    )

    assert (
        await dispatcher._send_result(  # noqa: SLF001
            MessageEventResult(
                type=EventResultType.CHAIN,
                chain=MessageChain([Plain("from-result")]),
            ),
            event,
            ctx,
        )
        is True
    )
    assert (
        await dispatcher._send_result(  # noqa: SLF001
            MessageChain([Plain("from-chain")]),
            event,
            ctx,
        )
        is True
    )
    assert (
        await dispatcher._send_result(  # noqa: SLF001
            [Plain("from-list")],
            event,
            ctx,
        )
        is True
    )

    assert [item["kind"] for item in peer.sent_messages] == ["chain", "chain", "chain"]
