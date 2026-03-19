from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest
from astrbot_sdk.protocol.descriptors import (
    CommandRouteSpec,
    CommandTrigger,
    HandlerDescriptor,
    PlatformFilterSpec,
)

from astrbot.core.sdk_bridge.plugin_bridge import SdkPluginBridge
from tests.fixtures.mocks import mock_discord_modules, mock_telegram_modules


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
