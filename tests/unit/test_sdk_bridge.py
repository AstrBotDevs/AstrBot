from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from astrbot_sdk.message_components import At, AtAll, Plain, Reply
from astrbot_sdk.messages import MessageChain
from astrbot_sdk.results import Propagation, message_result

from astrbot.core.message import components as core_comp
from astrbot.core.message.message_event_result import (
    MessageChain as CoreMessageChain,
)
from astrbot.core.message.message_event_result import (
    MessageEventResult,
)
from astrbot.core.platform.message_type import MessageType as CoreMessageType
from astrbot.core.star.sdk_bridge import SDKPluginBridge, is_sdk_plugin_dir
from astrbot.core.star.sdk_bridge.convert import (
    apply_sdk_result,
    to_core_chain,
    to_sdk_event,
)
from astrbot.core.star.star import star_map, star_registry
from astrbot.core.star.star_handler import EventType, star_handlers_registry


class FakeCoreEvent:
    """Minimal AstrMessageEvent stand-in for bridge tests."""

    def __init__(self, text: str = "greet 2", components=None) -> None:
        self._components = components
        self.unified_msg_origin = "webchat:FriendMessage:user-1"
        # The real AstrMessageEvent carries the id on message_obj, not on itself.
        self.message_obj = SimpleNamespace(message_id="m-1")
        self.role = "member"
        self.is_wake = True
        self.is_at_or_wake_command = True
        self.plugins_name = None
        self._text = text
        # The real AstrMessageEvent exposes the raw text as an attribute too
        # (CommandGroupFilter reads it directly).
        self.message_str = text
        self._extras: dict[str, Any] = {}
        self._result = None
        self._stopped = False
        self._has_send_oper = False

    def get_platform_name(self):
        return "webchat"

    def get_message_type(self):
        # Mirrors the real event: the message type lives in the UMO string.
        return CoreMessageType(self.unified_msg_origin.split(":", 2)[1])

    def get_messages(self):
        if self._components is not None:
            return self._components
        return [core_comp.Plain(self._text)]

    def get_message_str(self):
        return self._text

    def get_sender_id(self):
        return "user-1"

    def get_sender_name(self):
        return "Moon"

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def set_result(self, result):
        self._result = result

    def get_result(self):
        return self._result

    def clear_result(self):
        self._result = None

    def stop_event(self):
        self._stopped = True

    def is_stopped(self):
        return self._stopped


class FakeKVStore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str, str], Any] = {}

    async def put_async(self, scope, plugin_id, key, value):
        self.data[(scope, plugin_id, key)] = value

    async def get_async(self, scope, plugin_id, key, default=None):
        return self.data.get((scope, plugin_id, key), default)

    async def remove_async(self, scope, plugin_id, key):
        self.data.pop((scope, plugin_id, key), None)


def test_is_sdk_plugin_dir(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "metadata.yaml").write_text("name: legacy\nauthor: a\n", "utf-8")
    assert not is_sdk_plugin_dir(legacy)

    sdk = tmp_path / "sdk"
    sdk.mkdir()
    (sdk / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "runtime": {"api": "sdk"},
            },
        ),
        "utf-8",
    )
    assert is_sdk_plugin_dir(sdk)

    assert not is_sdk_plugin_dir(tmp_path / "missing")


def test_to_sdk_event_converts_core_event() -> None:
    event = FakeCoreEvent(
        components=[
            core_comp.Plain("hello "),
            core_comp.At(qq="123", name="Moon"),
            core_comp.AtAll(),
        ],
    )
    sdk_event = to_sdk_event(
        event,
        command_path="greet",
        arguments={"times": 2},
    )
    assert sdk_event.umo.platform_id == "webchat"
    assert sdk_event.umo.session_id == "user-1"
    assert sdk_event.is_private
    assert sdk_event.platform_type == "webchat"
    assert sdk_event.sender.name == "Moon"
    assert sdk_event.command is not None
    assert sdk_event.command.path == "greet"
    assert sdk_event.command.arguments == {"times": 2}

    chain = sdk_event.message
    assert isinstance(chain[0], Plain) and chain[0].text == "hello "
    assert isinstance(chain[1], At) and chain[1].user_id == "123"
    assert isinstance(chain[2], AtAll)


def test_to_core_chain_converts_outbound() -> None:
    chain = MessageChain(
        Plain("hi"),
        At(user_id="42", name="Moon"),
        AtAll(),
        Reply(id="m-9", sender_id="42", sender_name="Moon", text="quoted"),
    )
    components = to_core_chain(chain)
    assert isinstance(components[0], core_comp.Plain)
    assert components[0].text == "hi"
    assert isinstance(components[1], core_comp.At)
    assert str(components[1].qq) == "42"
    assert isinstance(components[2], core_comp.AtAll)
    assert isinstance(components[3], core_comp.Reply)
    assert str(components[3].id) == "m-9"


def test_apply_sdk_result_sets_result_and_stop() -> None:
    event = FakeCoreEvent()
    apply_sdk_result(event, message_result("hello", propagation=Propagation.STOP))
    result = event.get_result()
    assert isinstance(result, MessageEventResult)
    assert result.chain[0].text == "hello"
    assert event.is_stopped()


@pytest.mark.asyncio
async def test_bridge_message_handler_registration_and_invoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "msg_e2e"
    write_sdk_plugin(
        plugin_root,
        """
from astrbot_sdk import MessageEvent, on, Plugin
from astrbot_sdk.events import MessageType

class TestPlugin(Plugin):
    @on.message(
        message_types={MessageType.GROUP},
        regex=r"^echo\\s+",
        priority=5,
    )
    async def echo(self, event: MessageEvent):
        yield event.reply(f"echo: {event.text.strip()[5:].strip()}")
""",
        capabilities=[{"id": "message.receive"}],
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )

    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    full_name = f"sdk_bridge.{plugin_root.name}_echo"
    try:
        await bridge.start()
        handler = star_handlers_registry.star_handlers_map[full_name]
        assert handler.extras_configs["priority"] == 5

        # Regex + message type filters are compiled onto core filter objects.
        group_event = FakeCoreEvent("echo hello world")
        group_event.unified_msg_origin = "webchat:GroupMessage:group-1"
        assert all(f.filter(group_event, None) for f in handler.event_filters)

        private_event = FakeCoreEvent("echo hello")
        assert not all(f.filter(private_event, None) for f in handler.event_filters)

        non_match = FakeCoreEvent("hello")
        non_match.unified_msg_origin = "webchat:GroupMessage:group-1"
        assert not all(f.filter(non_match, None) for f in handler.event_filters)

        # The stub invokes the remote handler without command params.
        replies = []
        async for _ in handler.handler(group_event):
            if group_event.get_result():
                replies.append(group_event.get_result().chain[0].text)
            group_event.clear_result()
        assert replies == ["echo: hello world"]
    finally:
        await bridge.stop()

    assert full_name not in star_handlers_registry.star_handlers_map


@pytest.mark.asyncio
async def test_bridge_tool_registration_and_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "tool_e2e"
    write_sdk_plugin(
        plugin_root,
        """
from typing import Annotated

from astrbot_sdk import Plugin, on
from astrbot_sdk.tools import ToolCallContext

class TestPlugin(Plugin):
    @on.tool(name="get_weather", description="Get weather for a city")
    async def get_weather(
        self,
        call: ToolCallContext,
        city: Annotated[str, "City name"],
        days: int = 1,
    ) -> str:
        return f"{city}: sunny x{days} (call={bool(call.id)}, umo={call.umo is not None})"
""",
        capabilities=[{"id": "llm.tool.register"}],
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )

    from astrbot.core.provider.register import llm_tools

    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()

        tool = llm_tools.get_func("get_weather")
        assert tool is not None
        assert tool.description == "Get weather for a city"
        properties = tool.parameters["properties"]
        assert properties["city"]["type"] == "string"
        assert properties["city"]["description"] == "City name"
        assert properties["days"]["type"] == "number"

        # The tool is attributed to the bridge plugin so plugin-level
        # activation and per-plugin tool listing apply.
        assert tool.handler_module_path == bridge.module_path
        assert tool.active is True
        tool_handlers = [
            handler
            for handler in star_handlers_registry.get_handlers_by_module_name(
                bridge.module_path,
            )
            if handler.event_type == EventType.OnCallingFuncToolEvent
        ]
        assert len(tool_handlers) == 1
        assert tool_handlers[0].handler_name == "get_weather"
        assert tool_handlers[0].desc == "Get weather for a city"

        # The core tool executor invokes handler(event, **tool_args).
        event = FakeCoreEvent("weather?")
        result = await tool.handler(event, city="shanghai", days=3)
        assert result == "shanghai: sunny x3 (call=True, umo=True)"
    finally:
        await bridge.stop()

    assert llm_tools.get_func("get_weather") is None
    assert not [
        handler
        for handler in star_handlers_registry.get_handlers_by_module_name(
            bridge.module_path,
        )
        if handler.event_type == EventType.OnCallingFuncToolEvent
    ]


@pytest.mark.asyncio
async def test_bridge_respects_persisted_inactivation(
    tmp_path: Path,
    fake_bridge_sp,
) -> None:
    """A plugin disabled before a restart stays disabled, keeps its logo."""
    plugin_root = tmp_path / "disabled_e2e"
    write_sdk_plugin(
        plugin_root,
        """
from astrbot_sdk import Plugin, on

class TestPlugin(Plugin):
    @on.command("ping")
    async def ping(self, event):
        yield event.reply("pong")
""",
        capabilities=[{"id": "message.receive"}],
    )
    (plugin_root / "logo.png").write_bytes(b"png")
    module_path = f"sdk_bridge.{plugin_root.name}"
    fake_bridge_sp.data["inactivated_plugins"] = [module_path]

    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        metadata = star_map[module_path]
        assert metadata.activated is False
        assert metadata.logo_path == str(plugin_root / "logo.png")

        # Handlers stay registered (dashboard parity with in-process plugins)
        # but activation-filtered queries skip them.
        registered = star_handlers_registry.get_handlers_by_module_name(
            module_path,
        )
        assert registered
        visible = [
            handler
            for handler in star_handlers_registry.get_handlers_by_event_type(
                EventType.AdapterMessageEvent,
                only_activated=True,
            )
            if handler.handler_module_path == module_path
        ]
        assert visible == []
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_bridge_dynamic_tool_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "dyn_tool_e2e"
    write_sdk_plugin(
        plugin_root,
        """
from typing import Annotated

from astrbot_sdk import Plugin, lifecycle
from astrbot_sdk.tools import ToolDefinition

class TestPlugin(Plugin):
    @lifecycle.startup
    async def startup(self) -> None:
        async def server_time(zone: Annotated[str, "Timezone name"]) -> str:
            return f"noon in {zone}"

        self._tool_ref = await self.ctx.tools.register(
            ToolDefinition(
                name="server_time",
                description="Get the server time",
            ),
            server_time,
        )

    @lifecycle.shutdown
    async def shutdown(self, event) -> None:
        await self.ctx.tools.unregister(self._tool_ref)
""",
        capabilities=[{"id": "llm.tool.register"}],
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )

    from astrbot.core.provider.register import llm_tools

    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()

        # Registered during Runner startup with the derived string param.
        tool = llm_tools.get_func("server_time")
        assert tool is not None
        assert tool.parameters["properties"]["zone"]["type"] == "string"
        assert tool.parameters["properties"]["zone"]["description"] == "Timezone name"

        event = FakeCoreEvent("time?")
        assert await tool.handler(event, zone="UTC") == "noon in UTC"

        # Shutdown unregisters the tool from the core registry.
        await bridge.stop()
        assert llm_tools.get_func("server_time") is None
    finally:
        await bridge.stop()


def test_legacy_loader_skips_sdk_plugin_dirs(tmp_path: Path) -> None:
    from astrbot.core.star.star_manager import PluginManager

    legacy = tmp_path / "legacy_plugin"
    legacy.mkdir()
    (legacy / "main.py").write_text("# legacy", "utf-8")
    sdk = tmp_path / "sdk_plugin"
    sdk.mkdir()
    (sdk / "main.py").write_text("# sdk", "utf-8")
    (sdk / "metadata.yaml").write_text(
        yaml.safe_dump({"schema_version": 2, "runtime": {"api": "sdk"}}),
        "utf-8",
    )

    modules = PluginManager._get_modules(str(tmp_path))
    assert [m["pname"] for m in modules] == ["legacy_plugin"]


def test_legacy_loader_runtime_overrides(tmp_path: Path) -> None:
    from astrbot.core.star.star_manager import PluginManager

    legacy = tmp_path / "legacy_plugin"
    legacy.mkdir()
    (legacy / "main.py").write_text("# legacy", "utf-8")
    declared = tmp_path / "declared_isolated"
    declared.mkdir()
    (declared / "main.py").write_text("# declared", "utf-8")
    (declared / "metadata.yaml").write_text(
        yaml.safe_dump({"runtime": {"isolated": True}}),
        "utf-8",
    )

    # No overrides: plain legacy loads in-process, metadata-declared is skipped.
    modules = PluginManager._get_modules(str(tmp_path))
    assert [m["pname"] for m in modules] == ["legacy_plugin"]

    # Override into isolation: plain legacy is skipped too.
    modules = PluginManager._get_modules(
        str(tmp_path),
        {"legacy_plugin": "isolated"},
    )
    assert modules == []

    # Override back to in-process: metadata declaration is overridden.
    modules = PluginManager._get_modules(
        str(tmp_path),
        {"declared_isolated": "in-process"},
    )
    assert sorted(m["pname"] for m in modules) == [
        "declared_isolated",
        "legacy_plugin",
    ]


@pytest.mark.asyncio
async def test_load_all_honors_runtime_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDKPluginManager.load_all must apply runtime overrides when detecting
    isolated legacy plugins (previously the raw metadata check dropped
    override-isolated plugins, leaving them loaded nowhere)."""
    from astrbot.core.star.sdk_bridge import bridge as bridge_mod

    legacy = tmp_path / "legacy_plugin"
    legacy.mkdir()
    (legacy / "main.py").write_text("# legacy", "utf-8")

    started: list[tuple[str, bool]] = []

    class FakeBridge:
        def __init__(self, plugin_root, context, legacy=False, **kwargs):
            started.append((plugin_root.name, legacy))

        async def start(self) -> None:
            return None

    monkeypatch.setattr(bridge_mod, "SDKPluginBridge", FakeBridge)
    manager = bridge_mod.SDKPluginManager(context=None, plugin_store_path=tmp_path)

    # Without overrides a plain legacy plugin is not bridge-loaded.
    await manager.load_all()
    assert started == []

    # With the isolated override it is bridge-loaded in legacy mode.
    await manager.load_all(runtime_overrides={"legacy_plugin": "isolated"})
    assert started == [("legacy_plugin", True)]


def write_sdk_plugin(plugin_root: Path, source: str, *, capabilities=None) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": capabilities or []},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(source, "utf-8")


@pytest.mark.asyncio
async def test_bridge_rejects_non_python_language(tmp_path: Path) -> None:
    """Plugins declaring a language without a runner fail with a clear error."""
    plugin_root = tmp_path / "go_plugin"
    write_sdk_plugin(
        plugin_root,
        """
from astrbot_sdk import Plugin


class TestPlugin(Plugin):
    pass
""",
    )
    import yaml as _yaml

    metadata_path = plugin_root / "metadata.yaml"
    metadata = _yaml.safe_load(metadata_path.read_text("utf-8"))
    metadata["runtime"]["language"] = "go"
    metadata_path.write_text(_yaml.safe_dump(metadata), "utf-8")

    bridge = SDKPluginBridge(plugin_root, MagicMock())
    with pytest.raises(RuntimeError, match="runtime.language=go"):
        await bridge.start()


@pytest.mark.asyncio
async def test_bridge_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "bridge_e2e"
    write_sdk_plugin(
        plugin_root,
        """
from astrbot_sdk import MessageEvent, Plugin, on

class TestPlugin(Plugin):
    @on.command("greet")
    async def greet(self, event: MessageEvent, times: int, prefix: str = "hi"):
        count = await self.ctx.storage.get("count", 0) + 1
        await self.ctx.storage.set("count", count)
        for index in range(times):
            yield event.reply(f"{prefix} {event.sender.name} #{count}.{index}")
        await self.ctx.messages.send(event.umo, "done")
""",
        capabilities=[{"id": "message.send"}],
    )

    kv = FakeKVStore()
    monkeypatch.setattr("astrbot.core.star.sdk_bridge.services.storage.sp", kv)

    context = MagicMock()
    context.send_message = AsyncMock(return_value=True)

    bridge = SDKPluginBridge(plugin_root, context)
    full_name = f"sdk_bridge.{plugin_root.name}_greet"
    try:
        await bridge.start()

        # 注册到管线
        handler = star_handlers_registry.star_handlers_map[full_name]
        assert f"sdk_bridge.{plugin_root.name}" in star_map
        assert any(m.name == f"plugin_{plugin_root.name}" for m in star_registry)

        # 模拟 waking_check：指令匹配与参数解析
        event = FakeCoreEvent("greet 2")
        command_filter = handler.event_filters[0]
        assert command_filter.filter(event, None)
        parsed = event.get_extra("parsed_params")
        assert parsed == {"times": 2, "prefix": "hi"}

        # 模拟 star_request：驱动桥接 stub，验证 yield/ack 洋葱语义
        outputs = []
        async for _ in handler.handler(event, **parsed):
            result = event.get_result()
            outputs.append(result.chain[0].text if result else None)
            event.clear_result()
        assert outputs == ["hi Moon #1.0", "hi Moon #1.1"]

        # ctx.storage 经由 Host KV 持久化（插件命名空间）
        assert kv.data[("plugin", bridge.plugin_id, "count")] == 1

        # ctx.messages.send 经由 Context.send_message 主动发送
        context.send_message.assert_awaited_once()
        # 镜像进程内 event.send()：在飞事件被标记为已发送，管线跳过 LLM 阶段
        assert event._has_send_oper is True
        # 处理结束后在飞事件表清空
        assert bridge._inflight_events == {}
        session, chain = context.send_message.await_args.args
        assert session.platform_id == "webchat"
        assert session.message_type is CoreMessageType.FRIEND_MESSAGE
        assert session.session_id == "user-1"
        # Context.send_message requires a MessageChain with a .chain list.
        assert isinstance(chain, CoreMessageChain)
        assert chain.chain[0].text == "done"
    finally:
        await bridge.stop()

    assert full_name not in star_handlers_registry.star_handlers_map
    assert f"sdk_bridge.{plugin_root.name}" not in star_map


@pytest.mark.asyncio
async def test_bridge_rejects_mismatched_alias(tmp_path: Path) -> None:
    plugin_root = tmp_path / "bad_alias"
    write_sdk_plugin(
        plugin_root,
        """
from astrbot_sdk import Plugin, on

class TestPlugin(Plugin):
    @on.command("math add", aliases=("calc plus",))
    async def add(self, a: int, b: int):
        return str(a + b)
""",
    )
    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context)
    with pytest.raises(Exception, match="parent path"):
        await bridge.start()
    await bridge.stop()


def test_to_sdk_event_carries_plugins_name_extras() -> None:
    event = FakeCoreEvent()
    event.plugins_name = ["meme_manager", "astrbot"]

    sdk_event = to_sdk_event(event)

    assert sdk_event.extras["plugins_name"] == ["meme_manager", "astrbot"]

    event.plugins_name = None
    assert to_sdk_event(event).extras["plugins_name"] is None


class _FakeInflightEvent:
    """Stand-in for an in-flight Host AstrMessageEvent."""

    def __init__(self) -> None:
        self.call_llm = False
        self.calls: list[tuple[str, dict]] = []

    async def send_typing(self) -> None:
        self.calls.append(("send_typing", {}))

    async def stop_typing(self) -> None:
        self.calls.append(("stop_typing", {}))

    async def react(self, emoji: str) -> None:
        self.calls.append(("react", {"emoji": emoji}))

    async def get_group(self, group_id: str | None = None, **_kwargs: Any) -> Any:
        from astrbot.core.platform.astrbot_message import Group

        self.calls.append(("get_group", {"group_id": group_id}))
        if group_id is None:
            return None
        return Group(group_id=group_id, group_name="G")


@pytest.mark.asyncio
async def test_event_state_service_set_call_llm() -> None:
    from astrbot.core.star.sdk_bridge.services import EventStateService

    first, second = _FakeInflightEvent(), _FakeInflightEvent()
    inflight = {"webchat:FriendMessage:user-1": [first, second]}
    service = EventStateService(inflight)

    await service.handle(
        "set_call_llm",
        {"umo": "webchat:FriendMessage:user-1", "value": True},
    )

    assert first.call_llm is True
    assert second.call_llm is True


@pytest.mark.asyncio
async def test_event_state_service_call_method() -> None:
    from astrbot_sdk.errors import InvalidRequest, NotFound

    from astrbot.core.star.sdk_bridge.services import EventStateService

    event = _FakeInflightEvent()
    service = EventStateService({"webchat:FriendMessage:user-1": [event]})

    await service.handle(
        "call_method",
        {"umo": "webchat:FriendMessage:user-1", "method": "send_typing"},
    )
    await service.handle(
        "call_method",
        {
            "umo": "webchat:FriendMessage:user-1",
            "method": "react",
            "args": {"emoji": "👍"},
        },
    )
    assert event.calls == [
        ("send_typing", {}),
        ("react", {"emoji": "👍"}),
    ]

    result = await service.handle(
        "call_method",
        {
            "umo": "webchat:FriendMessage:user-1",
            "method": "get_group",
            "args": {"group_id": "g-1"},
        },
    )
    assert result["result"]["group_id"] == "g-1"
    assert result["result"]["group_name"] == "G"

    # Methods outside the allowlist never reach the event.
    with pytest.raises(NotFound):
        await service.handle(
            "call_method",
            {"umo": "webchat:FriendMessage:user-1", "method": "stop_event"},
        )
    # Without an in-flight event there is nothing to forward to.
    with pytest.raises(NotFound):
        await service.handle(
            "call_method",
            {"umo": "webchat:FriendMessage:nobody", "method": "send_typing"},
        )
    with pytest.raises(InvalidRequest):
        await service.handle("call_method", {"method": "send_typing"})


def test_snapshot_platform_entry_redacts_config() -> None:
    from astrbot.core.star.sdk_bridge.snapshot import _platform_entries

    instance = SimpleNamespace(
        config={"appid": "123", "app_secret": "s3cret", "token": "abc"},
    )
    instance.meta = lambda: SimpleNamespace(
        id="qq-1",
        name="qq_official",
        description="d",
        adapter_display_name="QQ",
    )

    entries = _platform_entries([instance])

    assert entries[0]["id"] == "qq-1"
    assert entries[0]["config"]["appid"] == "123"
    assert entries[0]["config"]["app_secret"] == ""
    assert entries[0]["config"]["token"] == ""
