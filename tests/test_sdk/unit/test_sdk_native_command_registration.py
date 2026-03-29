from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.protocol.descriptors import (
    CommandRouteSpec,
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    Permissions,
    PlatformFilterSpec,
    ScheduleTrigger,
)

from astrbot.core.command_compatibility import (
    CommandRegistration,
    build_cross_system_conflicts,
)
from astrbot.core.sdk_bridge.plugin_bridge import SdkHandlerRef, SdkPluginBridge

pytest_plugins = (
    "tests.fixtures.mocks.discord",
    "tests.fixtures.mocks.telegram",
)


class _BridgeStarContext:
    def __init__(self) -> None:
        self.registered_web_apis = []
        self.cron_manager = None
        self.platform_manager = SimpleNamespace(
            refresh_native_commands=AsyncMock(),
        )

    def get_all_stars(self) -> list[object]:
        return []


class _DispatchEvent:
    def __init__(self, text: str, *, is_admin: bool = False) -> None:
        self._text = text
        self._is_admin = is_admin
        self._stopped = False
        self._result = None
        self._has_send_oper = False
        self.call_llm = False
        self.unified_msg_origin = "telegram:friend:session"

    def is_stopped(self) -> bool:
        return self._stopped

    def stop_event(self) -> None:
        self._stopped = True

    def set_result(self, result) -> None:
        self._result = result

    def get_platform_name(self) -> str:
        return "telegram"

    def get_message_str(self) -> str:
        return self._text

    def is_admin(self) -> bool:
        return self._is_admin

    def should_call_llm(self, call_llm: bool) -> None:
        self.call_llm = call_llm


@pytest.mark.unit
def test_sdk_bridge_native_command_candidates_collapse_grouped_commands() -> None:
    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._records = {  # noqa: SLF001
        "ai_girlfriend": SimpleNamespace(
            plugin=SimpleNamespace(
                name="ai_girlfriend",
                manifest_data={"support_platforms": ["telegram", "discord"]},
            ),
            load_order=0,
            state="enabled",
            handlers=[
                SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.chat",
                        trigger=CommandTrigger(
                            command="gf chat",
                            description="Switch to AI girlfriend persona",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf chat",
                            group_help="AI girlfriend commands",
                        ),
                    ),
                    declaration_order=0,
                ),
                SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.affection",
                        trigger=CommandTrigger(
                            command="gf affection",
                            description="Show affection level",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf affection",
                            group_help="AI girlfriend commands",
                        ),
                    ),
                    declaration_order=1,
                ),
                SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.discord_only",
                        trigger=CommandTrigger(
                            command="secret",
                            description="Discord only command",
                        ),
                        filters=[PlatformFilterSpec(platforms=["discord"])],
                    ),
                    declaration_order=2,
                ),
            ],
            dynamic_command_routes=[],
            session=None,
        )
    }

    telegram_commands = bridge.list_native_command_candidates("telegram")
    assert telegram_commands == [
        {
            "name": "gf",
            "description": "AI girlfriend commands",
            "is_group": True,
        }
    ]

    discord_commands = bridge.list_native_command_candidates("discord")
    assert discord_commands == [
        {
            "name": "gf",
            "description": "AI girlfriend commands",
            "is_group": True,
        },
        {
            "name": "secret",
            "description": "Discord only command",
            "is_group": False,
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_message_falls_back_to_group_root_help(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._records = {  # noqa: SLF001
        "ai_girlfriend": SimpleNamespace(
            plugin=SimpleNamespace(
                name="ai_girlfriend",
                manifest_data={"support_platforms": ["telegram"]},
            ),
            plugin_id="ai_girlfriend",
            load_order=0,
            state="enabled",
            handlers=[
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.chat",
                        trigger=CommandTrigger(
                            command="gf chat",
                            description="Switch to AI girlfriend persona",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf chat",
                            group_help="AI girlfriend commands",
                        ),
                    ),
                    declaration_order=0,
                ),
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.affection",
                        trigger=CommandTrigger(
                            command="gf affection",
                            description="Show affection level",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf affection",
                            group_help="AI girlfriend commands",
                        ),
                    ),
                    declaration_order=1,
                ),
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.catchall",
                        trigger=MessageTrigger(regex=r"(?s)^.*$"),
                    ),
                    declaration_order=2,
                ),
            ],
            dynamic_command_routes=[],
            session=None,
        )
    }
    event = _DispatchEvent("/gf")

    result = await bridge.dispatch_message(event)

    assert result.stopped is True
    assert event._stopped is True
    assert event.call_llm is True
    assert event._result is not None
    assert event._result.get_plain_text().startswith("gf命令：")
    assert "/gf chat" in event._result.get_plain_text()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_message_returns_permission_denied_for_admin_subcommand(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._records = {  # noqa: SLF001
        "ai_girlfriend": SimpleNamespace(
            plugin=SimpleNamespace(
                name="ai_girlfriend",
                manifest_data={"support_platforms": ["telegram"]},
            ),
            plugin_id="ai_girlfriend",
            load_order=0,
            state="enabled",
            handlers=[
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.public",
                        trigger=CommandTrigger(
                            command="gf status",
                            description="Show status",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf status",
                            group_help="AI girlfriend commands",
                        ),
                    ),
                    declaration_order=0,
                ),
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.admin",
                        trigger=CommandTrigger(
                            command="gf sync",
                            description="Sync data",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf sync",
                            group_help="AI girlfriend commands",
                        ),
                        permissions=Permissions(require_admin=True),
                    ),
                    declaration_order=1,
                ),
            ],
            dynamic_command_routes=[],
            session=None,
        )
    }
    event = _DispatchEvent("/gf sync")

    result = await bridge.dispatch_message(event)

    assert result.stopped is True
    assert event._stopped is True
    assert event._result is not None
    assert event._result.get_plain_text() == "权限不足：`/gf sync` 需要管理员权限。"


@pytest.mark.unit
def test_sdk_bridge_refresh_command_compatibility_issues_keeps_existing_state(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.collect_legacy_command_registrations",
        lambda *args, **kwargs: [
            CommandRegistration(
                runtime_kind="legacy",
                plugin_name="legacy-demo",
                plugin_display_name="Legacy Demo",
                handler_full_name="legacy.demo.hello",
                command_name="hello",
            )
        ],
    )

    bridge = SdkPluginBridge(_BridgeStarContext())
    record = SimpleNamespace(
        plugin=SimpleNamespace(
            name="sdk-demo",
            manifest_data={
                "display_name": "SDK Demo",
                "support_platforms": ["telegram"],
            },
        ),
        plugin_id="sdk-demo",
        load_order=0,
        state="custom_partial_state",
        unsupported_features=[],
        handlers=[
            SdkHandlerRef(
                descriptor=HandlerDescriptor(
                    id="sdk-demo:main.hello",
                    trigger=CommandTrigger(command="hello"),
                ),
                declaration_order=0,
            )
        ],
        dynamic_command_routes=[],
        issues=[],
    )
    bridge._records = {"sdk-demo": record}  # noqa: SLF001

    bridge.refresh_command_compatibility_issues()

    assert record.state == "custom_partial_state"
    assert record.issues[0]["warning_type"] == bridge.COMMAND_OVERRIDE_WARNING_TYPE
    assert "overrides legacy plugin" in record.issues[0]["details"]
    assert record.issues[0]["command_name"] == "hello"

    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.collect_legacy_command_registrations",
        lambda *args, **kwargs: [],
    )

    bridge.refresh_command_compatibility_issues()

    assert record.state == "custom_partial_state"
    assert record.issues == []


@pytest.mark.unit
def test_cross_system_command_conflicts_detect_command_namespace_overlap() -> None:
    conflicts = build_cross_system_conflicts(
        [
            CommandRegistration(
                runtime_kind="legacy",
                plugin_name="legacy-demo",
                plugin_display_name="Legacy Demo",
                handler_full_name="legacy.demo.gf",
                command_name="gf",
            )
        ],
        [
            CommandRegistration(
                runtime_kind="sdk",
                plugin_name="sdk-demo",
                plugin_display_name="SDK Demo",
                handler_full_name="sdk-demo:main.chat",
                command_name="gf chat",
            )
        ],
    )

    assert len(conflicts) == 1
    assert conflicts[0].command_name == "gf <> gf chat"
    assert conflicts[0].legacy.command_name == "gf"
    assert conflicts[0].sdk.command_name == "gf chat"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_group_root_help_hides_admin_commands_for_non_admin(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._records = {  # noqa: SLF001
        "ai_girlfriend": SimpleNamespace(
            plugin=SimpleNamespace(
                name="ai_girlfriend",
                manifest_data={"support_platforms": ["telegram"]},
            ),
            plugin_id="ai_girlfriend",
            load_order=0,
            state="enabled",
            handlers=[
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.public",
                        trigger=CommandTrigger(
                            command="gf status",
                            description="Show status",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf status",
                            group_help="AI girlfriend commands",
                        ),
                    ),
                    declaration_order=0,
                ),
                SdkHandlerRef(
                    descriptor=HandlerDescriptor(
                        id="ai_girlfriend:main.admin",
                        trigger=CommandTrigger(
                            command="gf sync",
                            description="Sync data",
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf sync",
                            group_help="AI girlfriend commands",
                        ),
                        permissions=Permissions(require_admin=True),
                    ),
                    declaration_order=1,
                ),
            ],
            dynamic_command_routes=[],
            session=None,
        )
    }
    event = _DispatchEvent("/gf")

    result = await bridge.dispatch_message(event)

    assert result.stopped is True
    assert event._result is not None
    assert "/gf status" in event._result.get_plain_text()
    assert "/gf sync" not in event._result.get_plain_text()


@pytest.mark.unit
def test_telegram_collect_commands_includes_sdk_candidates(
    mock_telegram_modules,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules["telegram.ext"].ContextTypes.DEFAULT_TYPE = object
    from astrbot.core.platform.sources.telegram import tg_adapter

    monkeypatch.setattr(tg_adapter, "star_handlers_registry", [])
    monkeypatch.setattr(tg_adapter, "star_map", {})
    monkeypatch.setattr(
        tg_adapter,
        "BotCommand",
        lambda command, description: SimpleNamespace(
            command=command,
            description=description,
        ),
    )

    adapter = tg_adapter.TelegramPlatformAdapter(
        {"telegram_token": "test-token", "id": "telegram-test"},
        {},
        asyncio.Queue(),
    )
    adapter.sdk_plugin_bridge = SimpleNamespace(
        list_native_command_candidates=lambda platform_name: (
            [
                {
                    "name": "gf",
                    "description": "AI girlfriend commands",
                    "is_group": True,
                }
            ]
            if platform_name == "telegram"
            else []
        )
    )

    commands = adapter.collect_commands()

    assert [(item.command, item.description) for item in commands] == [
        ("gf", "AI girlfriend commands")
    ]


@pytest.mark.unit
def test_discord_collect_commands_includes_sdk_candidates(
    mock_discord_modules,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )

    monkeypatch.setattr(
        "astrbot.core.platform.sources.discord.discord_platform_adapter.star_handlers_registry",
        [],
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.discord.discord_platform_adapter.star_map", {}
    )

    adapter = DiscordPlatformAdapter(
        {"discord_token": "test-token", "id": "discord-test"},
        {},
        asyncio.Queue(),
    )
    adapter.sdk_plugin_bridge = SimpleNamespace(
        list_native_command_candidates=lambda platform_name: (
            [
                {
                    "name": "gf",
                    "description": "AI girlfriend commands",
                    "is_group": True,
                }
            ]
            if platform_name == "discord"
            else []
        )
    )

    assert adapter.collect_commands() == [("gf", "AI girlfriend commands")]


@pytest.mark.unit
def test_sdk_bridge_refresh_native_platform_commands_delegates_to_platform_manager() -> (
    None
):
    star_context = _BridgeStarContext()
    bridge = SdkPluginBridge(star_context)

    asyncio.run(bridge._refresh_native_platform_commands({"telegram"}))  # noqa: SLF001

    star_context.platform_manager.refresh_native_commands.assert_awaited_once_with(
        platforms={"telegram"}
    )


@pytest.mark.unit
def test_sdk_bridge_reload_plugin_refreshes_telegram_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_BridgeStarContext())
    plugin = SimpleNamespace(name="astrbot_plugin_moodlog")
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.discover_plugins",
        lambda _plugins_dir: SimpleNamespace(plugins=[plugin], issues=[]),
    )
    bridge.env_manager.plan = lambda _plugins: None  # type: ignore[method-assign]
    monkeypatch.setattr(bridge, "_set_discovery_issues", lambda _issues: None)
    load_mock = AsyncMock()
    refresh_mock = AsyncMock()
    monkeypatch.setattr(bridge, "_load_or_reload_plugin", load_mock)
    monkeypatch.setattr(bridge, "_refresh_native_platform_commands", refresh_mock)

    asyncio.run(bridge.reload_plugin("astrbot_plugin_moodlog"))

    load_mock.assert_awaited_once_with(
        plugin,
        load_order=0,
        reset_restart_budget=True,
    )
    refresh_mock.assert_awaited_once_with({"telegram"})


@pytest.mark.unit
def test_sdk_bridge_dashboard_handler_items_use_real_descriptions_and_fallbacks() -> (
    None
):
    bridge = SdkPluginBridge(_BridgeStarContext())

    command_item = bridge._handler_to_dashboard_item(  # noqa: SLF001
        SdkHandlerRef(
            descriptor=HandlerDescriptor(
                id="ai_girlfriend:main.chat",
                trigger=CommandTrigger(
                    command="gf chat",
                    description="Switch to AI girlfriend persona",
                ),
            ),
            declaration_order=0,
        )
    )
    fallback_command_item = bridge._handler_to_dashboard_item(  # noqa: SLF001
        SdkHandlerRef(
            descriptor=HandlerDescriptor(
                id="ai_girlfriend:main.mood",
                trigger=CommandTrigger(command="gf mood"),
            ),
            declaration_order=1,
        )
    )
    message_item = bridge._handler_to_dashboard_item(  # noqa: SLF001
        SdkHandlerRef(
            descriptor=HandlerDescriptor(
                id="ai_girlfriend:main.memory",
                trigger=MessageTrigger(keywords=["memory"]),
                description="Capture structured memory hints",
            ),
            declaration_order=2,
        )
    )
    event_item = bridge._handler_to_dashboard_item(  # noqa: SLF001
        SdkHandlerRef(
            descriptor=HandlerDescriptor(
                id="ai_girlfriend:main.waiting",
                trigger=EventTrigger(event_type="waiting_llm_request"),
            ),
            declaration_order=3,
        )
    )
    schedule_item = bridge._handler_to_dashboard_item(  # noqa: SLF001
        SdkHandlerRef(
            descriptor=HandlerDescriptor(
                id="ai_girlfriend:main.maintenance",
                trigger=ScheduleTrigger(interval_seconds=60),
            ),
            declaration_order=4,
        )
    )

    assert command_item["event_type_h"] == "SDK 指令触发"
    assert command_item["desc"] == "Switch to AI girlfriend persona"
    assert command_item["type"] == "指令"
    assert command_item["cmd"] == "gf chat"

    assert fallback_command_item["desc"] == "Command: gf mood"

    assert message_item["event_type_h"] == "SDK 消息触发"
    assert message_item["desc"] == "Capture structured memory hints"
    assert message_item["type"] == "关键词"
    assert message_item["cmd"] == "memory"

    assert event_item["event_type_h"] == "SDK 事件触发"
    assert event_item["desc"] == "无描述"
    assert event_item["type"] == "事件"
    assert event_item["cmd"] == "waiting_llm_request"

    assert schedule_item["event_type_h"] == "SDK 定时触发"
    assert schedule_item["desc"] == "无描述"
    assert schedule_item["type"] == "定时"
    assert schedule_item["cmd"] == "60"


@pytest.mark.unit
def test_sdk_bridge_lists_dashboard_commands_and_tools(tmp_path) -> None:
    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._records = {  # noqa: SLF001
        "sdk-demo": SimpleNamespace(
            plugin=SimpleNamespace(
                name="sdk-demo",
                plugin_dir=tmp_path / "sdk-demo",
                manifest_data={"display_name": "SDK Demo"},
            ),
            plugin_id="sdk-demo",
            load_order=0,
            state="enabled",
            handlers=[
                SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.chat",
                        trigger=CommandTrigger(
                            command="gf chat",
                            description="Chat with the SDK plugin",
                            aliases=["girl chat"],
                        ),
                        command_route=CommandRouteSpec(
                            group_path=["gf"],
                            display_command="gf chat",
                            group_help="SDK group help",
                        ),
                    ),
                    declaration_order=0,
                ),
                SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.ping",
                        trigger=CommandTrigger(command="ping"),
                    ),
                    declaration_order=1,
                ),
            ],
            llm_tools={
                "memory.search": LLMToolSpec.create(
                    name="memory.search",
                    description="Search SDK memory",
                    parameters_schema={"type": "object", "properties": {}},
                    active=True,
                )
            },
            dynamic_command_routes=[],
            session=None,
        )
    }

    commands = bridge.list_dashboard_commands()
    tools = bridge.list_dashboard_tools()

    group = next(item for item in commands if item["type"] == "group")
    assert group["command_key"] == "sdk:group:sdk-demo:gf"
    assert group["effective_command"] == "gf"
    assert group["description"] == "SDK group help"
    assert group["sub_commands"][0]["effective_command"] == "gf chat"
    assert group["sub_commands"][0]["aliases"] == ["girl chat"]

    root_command = next(
        item for item in commands if item["effective_command"] == "ping"
    )
    assert root_command["command_key"] == "sdk:command:sdk-demo:sdk-demo:main.ping"
    assert root_command["runtime_kind"] == "sdk"
    assert root_command["supports_toggle"] is False

    assert tools == [
        {
            "tool_key": "sdk:sdk-demo:memory.search",
            "name": "memory.search",
            "description": "Search SDK memory",
            "parameters": {"type": "object", "properties": {}},
            "active": True,
            "origin": "sdk_plugin",
            "origin_name": "SDK Demo",
            "runtime_kind": "sdk",
            "plugin_id": "sdk-demo",
        }
    ]
