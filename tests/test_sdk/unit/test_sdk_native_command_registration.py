from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest
from astrbot_sdk.protocol.descriptors import (
    CommandRouteSpec,
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    PlatformFilterSpec,
    ScheduleTrigger,
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

    def get_all_stars(self) -> list[object]:
        return []


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
def test_telegram_collect_commands_includes_sdk_candidates(
    mock_telegram_modules,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules["telegram.ext"].ContextTypes.DEFAULT_TYPE = object
    from astrbot.core.platform.sources.telegram import tg_adapter

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
) -> None:
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
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
