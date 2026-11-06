import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.discord import discord_platform_adapter
from astrbot.core.platform.sources.discord.discord_platform_adapter import (
    DiscordPlatformAdapter,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)
from astrbot.core.umop_config_router import UmopConfigRouter


@pytest.fixture
def config_manager():
    preferences = Mock()
    router = UmopConfigRouter(preferences)
    manager = AstrBotConfigManager({"plugin_set": ["*"]}, router, preferences)
    manager.confs.update(
        blocked={"plugin_set": []},
        demo={"plugin_set": ["demo_plugin"]},
        other={"plugin_set": ["other_plugin"]},
        missing_key={"timezone": "UTC"},
        mixed_star={"plugin_set": ["*", "demo_plugin"]},
        null_plugins={"plugin_set": None},
    )
    manager.abconf_data = {
        key: {"name": key, "path": f"{key}.json"}
        for key in manager.confs
        if key != "default"
    }
    manager.confs["orphaned"] = {"plugin_set": ["demo_plugin"]}
    manager.abconf_data["unloaded"] = {"name": "Unloaded", "path": "missing.json"}
    return manager


@pytest.fixture
def command_registry(monkeypatch):
    registry = StarHandlerRegistry()
    plugins = {}
    for name, plugin_name, reserved, activated, enabled in (
        ("demo", "demo_plugin", False, True, True),
        ("other", "other_plugin", False, True, True),
        ("help", "builtin", True, True, True),
        ("inactive", "inactive_plugin", False, False, True),
        ("disabled", "demo_plugin", False, True, False),
    ):
        module = f"test_plugins.{name}"
        plugins[module] = StarMetadata(
            name=plugin_name,
            module_path=module,
            reserved=reserved,
            activated=activated,
        )
        registry.append(
            StarHandlerMetadata(
                event_type=EventType.AdapterMessageEvent,
                handler_full_name=f"{module}.{name}",
                handler_name=name,
                handler_module_path=module,
                handler=AsyncMock(),
                event_filters=[CommandFilter(name)],
                enabled=enabled,
                desc=f"Run {name}",
            )
        )
    monkeypatch.setattr(discord_platform_adapter, "star_handlers_registry", registry)
    monkeypatch.setattr(discord_platform_adapter, "star_map", plugins)
    return registry, plugins


@pytest.mark.asyncio
async def test_two_discord_bots_only_register_their_enabled_plugins(
    config_manager, command_registry
):
    config_manager.ucr.umop_to_conf_id = {"bot_b:*:*": "blocked"}
    registered = {}
    for platform_id in ("bot_a", "bot_b"):
        adapter = DiscordPlatformAdapter({"id": platform_id}, {}, asyncio.Queue())
        adapter.astrbot_config_mgr = config_manager
        adapter.client = SimpleNamespace(
            add_application_command=Mock(), sync_commands=AsyncMock()
        )

        await adapter._collect_and_register_commands()

        registered[platform_id] = {
            call.args[0].name
            for call in adapter.client.add_application_command.call_args_list
        }
        adapter.client.sync_commands.assert_awaited_once()

    assert registered == {"bot_a": {"demo", "other", "help"}, "bot_b": {"help"}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("routes", "default_plugins", "expected"),
    [
        ({"bot:*:*": "demo"}, ["*"], {"demo", "help"}),
        ({"bot_*::": "blocked"}, ["*"], {"help"}),
        ({"::": "blocked"}, ["*"], {"help"}),
        ({"other_bot:*:*": "blocked"}, ["*"], {"demo", "other", "help"}),
        ({"bot:*:*": "missing"}, ["other_plugin"], {"other", "help"}),
        ({"bot:*:*": "missing_key"}, [], {"demo", "other", "help"}),
        ({"bot:*:*": "orphaned"}, ["other_plugin"], {"other", "help"}),
        ({"bot:*:*": "unloaded"}, ["other_plugin"], {"other", "help"}),
        ({"bot:*:*": "mixed_star"}, [], {"demo", "help"}),
        ({"bot:*:*": "null_plugins"}, [], {"demo", "other", "help"}),
        ({}, [], {"help"}),
        ({"invalid": "demo", "bot:*:*": "blocked"}, ["*"], {"help"}),
        (
            {"bot:GroupMessage:123": "demo", "bot:*:*": "missing_key"},
            [],
            {"demo", "other", "help"},
        ),
        (
            {"bot:GroupMessage:123": "demo", "bot:*:*": "blocked"},
            [],
            {"demo", "help"},
        ),
        (
            {"bot:GroupMessage:*": "demo", "bot:FriendMessage:*": "other"},
            ["*"],
            {"demo", "other", "help"},
        ),
        (
            {"bot:GroupMessage:*": "blocked"},
            ["other_plugin"],
            {"other", "help"},
        ),
        (
            {"bot:GroupMessage:123": "demo"},
            ["other_plugin"],
            {"demo", "other", "help"},
        ),
        (
            {"bot:*:*": "blocked", "bot:GroupMessage:123": "demo"},
            ["*"],
            {"help"},
        ),
        (
            {
                "bot:GroupMessage:123": "blocked",
                "*:GroupMessage:123": "demo",
                "bot:*:*": "blocked",
            },
            ["*"],
            {"help"},
        ),
        (
            {
                "bot:GroupMessage:12*": "blocked",
                "bot:GroupMessage:123": "demo",
                "bot:*:*": "blocked",
            },
            ["*"],
            {"help"},
        ),
        (
            {"bot:OtherMessage:*": "demo", "bot:*:*": "blocked"},
            ["*"],
            {"help"},
        ),
    ],
)
async def test_discord_registration_uses_bot_profile_union(
    config_manager, command_registry, routes, default_plugins, expected
):
    config_manager.default_conf["plugin_set"] = default_plugins
    config_manager.ucr.umop_to_conf_id = routes
    adapter = DiscordPlatformAdapter({"id": "bot"}, {}, asyncio.Queue())
    if any(pattern.startswith("bot_") for pattern in routes):
        adapter.config["id"] = "bot_test"
    adapter.astrbot_config_mgr = config_manager
    adapter.client = SimpleNamespace(
        add_application_command=Mock(), sync_commands=AsyncMock()
    )

    await adapter._collect_and_register_commands()

    assert {
        call.args[0].name
        for call in adapter.client.add_application_command.call_args_list
    } == expected
    adapter.client.sync_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_registration_without_manager_keeps_existing_behavior(
    command_registry,
):
    adapter = DiscordPlatformAdapter({"id": "bot"}, {}, asyncio.Queue())
    adapter.client = SimpleNamespace(
        add_application_command=Mock(), sync_commands=AsyncMock()
    )

    await adapter._collect_and_register_commands()

    assert {
        call.args[0].name
        for call in adapter.client.add_application_command.call_args_list
    } == {"demo", "other", "help"}


@pytest.mark.parametrize(
    "routes",
    [
        {
            "bot:GroupMessage:1?": "demo",
            "bot:GroupMessage:12": "other",
            "bot:*:*": "blocked",
        },
        {"bot*:[GF]*:12[0-9]": "demo", "::": "other"},
        {"bot::thread:*": "demo", "bot::": "blocked"},
        {"bot:GroupMessage:?": "blocked", "bot:GroupMessage:*": "other"},
    ],
)
def test_platform_profile_union_never_hides_sampled_session_config(
    config_manager, routes
):
    config_manager.ucr.umop_to_conf_id = routes
    message_types = (MessageType.GROUP_MESSAGE, MessageType.FRIEND_MESSAGE)
    for platform_id in ("bot", "bot_test", "other_bot"):
        profiles = config_manager.get_platform_configs(platform_id, message_types)
        for message_type in message_types:
            for session_id in (
                "",
                "1",
                "12",
                "123",
                "139",
                "abc",
                "thread:member",
                "321_123",
            ):
                session = MessageSession(platform_id, message_type, session_id)
                actual = config_manager.get_conf(str(session))
                assert any(profile is actual for profile in profiles), str(session)


@pytest.mark.asyncio
async def test_platform_manager_injects_profiles_without_changing_adapter_constructor(
    monkeypatch, config_manager
):
    from astrbot.core.platform import manager as manager_module

    adapter = SimpleNamespace(client_self_id="test-client")
    adapter_class = Mock(return_value=adapter)
    monkeypatch.setitem(manager_module.platform_cls_map, "test_scope", adapter_class)
    monkeypatch.setattr(
        manager_module.star_handlers_registry,
        "get_handlers_by_event_type",
        Mock(return_value=[]),
    )
    queue = asyncio.Queue()
    settings = {}
    manager = manager_module.PlatformManager(
        {"platform": [], "platform_settings": settings},
        queue,
        astrbot_config_mgr=config_manager,
    )

    def assert_injected_before_start(*args):
        assert adapter.astrbot_config_mgr is config_manager

    monkeypatch.setattr(
        manager, "_start_platform_task", Mock(side_effect=assert_injected_before_start)
    )
    platform_config = {"id": "bot", "type": "test_scope", "enable": True}

    await manager.load_platform(platform_config)

    adapter_class.assert_called_once_with(platform_config, settings, queue)
    assert adapter.astrbot_config_mgr is config_manager
    manager._start_platform_task.assert_called_once_with(
        "platform_test_scope_bot", adapter
    )
