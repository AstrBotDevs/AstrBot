import asyncio
from unittest.mock import Mock

import pytest

from tests.fixtures.mocks.discord import (
    MockDiscordBuilder,
    mock_discord_modules,  # noqa: F401
)


class DiscordSyncError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _build_adapter(monkeypatch: pytest.MonkeyPatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )

    monkeypatch.setattr(discord_platform_adapter, "star_handlers_registry", [])
    # The real ``discord`` module may already be bound to this adapter when the
    # rest of the suite imported it first. Stub the constructors the adapter
    # calls so the tests do not depend on ``sys.modules["discord"]`` being mocked
    # by ``mock_discord_modules``.
    monkeypatch.setattr(discord_platform_adapter.discord, "SlashCommand", Mock())
    monkeypatch.setattr(discord_platform_adapter.discord, "Option", Mock())
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "HTTPException",
        DiscordSyncError,
        raising=False,
    )

    adapter = DiscordPlatformAdapter(
        {"discord_command_register": True},
        {},
        asyncio.Queue(),
    )
    adapter.client = MockDiscordBuilder.create_client()
    return adapter


@pytest.mark.asyncio
async def test_discord_command_sync_ignores_daily_quota(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)
    warning = Mock()
    monkeypatch.setattr(discord_platform_adapter.logger, "warning", warning)
    adapter.client.sync_commands.side_effect = DiscordSyncError(
        "Max number of daily application command creates reached",
        code=30034,
    )

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once()
    warning.assert_called_once()
    assert "30034" in warning.call_args.args[0]


@pytest.mark.asyncio
async def test_discord_command_sync_keeps_going_after_unowned_handler(
    monkeypatch,
):
    """A handler owned by no plugin must not abort the whole sync loop.

    Regression test for https://github.com/AstrBotDevs/AstrBot/issues/10626:
    the old code subscripted ``star_map`` directly and raised ``KeyError``
    inside ``on_ready``, so no plugin's slash commands were registered at all.
    The unowned handler must be skipped while active plugins still register.
    """
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)

    orphan = Mock()
    orphan.handler_module_path = "some.unrelated.toolkit.helpers"  # owned by no plugin
    orphan.enabled = True
    orphan.event_filters = [object()]

    owned = Mock()
    owned.handler_module_path = "data.plugins.demo.main"
    owned.enabled = True
    owned.event_filters = [object()]

    plugin_md = Mock()
    plugin_md.activated = True
    plugin_md.reserved = False
    plugin_md.root_dir_name = "demo"
    monkeypatch.setattr(
        discord_platform_adapter, "star_handlers_registry", [orphan, owned]
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.demo.main": plugin_md},
    )

    cmd_info = ("demo_cmd", "demo description", object())
    extract = Mock(return_value=cmd_info)
    monkeypatch.setattr(adapter, "_extract_command_info", extract)

    await adapter._collect_and_register_commands()  # must not raise KeyError

    extract.assert_called_once()
    adapter.client.add_application_command.assert_called_once()
    adapter.client.sync_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_command_sync_registers_submodule_handler_of_active_plugin(
    monkeypatch,
):
    """A submodule handler whose owning plugin is activated must register.

    ``star_map`` is keyed by the plugin entry module, so a handler living in
    ``plugin/foo.py`` never matches exactly. The adapter resolves ownership by
    plugin package root; the command must reach Discord instead of being
    silently dropped.
    """
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)

    submodule_handler = Mock()
    submodule_handler.handler_module_path = "data.plugins.demo.mixin"
    submodule_handler.enabled = True
    submodule_handler.event_filters = [object()]

    active_plugin_md = Mock()
    active_plugin_md.activated = True
    active_plugin_md.reserved = False
    active_plugin_md.root_dir_name = "demo"
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [submodule_handler],
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.demo.main": active_plugin_md},
    )

    cmd_info = ("demo_cmd", "demo description", object())
    extract = Mock(return_value=cmd_info)
    monkeypatch.setattr(adapter, "_extract_command_info", extract)

    await adapter._collect_and_register_commands()

    extract.assert_called_once()
    adapter.client.add_application_command.assert_called_once()
    adapter.client.sync_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_command_sync_registers_package_root_handler_of_active_plugin(
    monkeypatch,
):
    """A handler defined in the plugin's ``__init__.py`` has a module path that
    equals the plugin package root exactly (no trailing submodule). It must
    still resolve to the plugin and register.
    """
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)

    root_handler = Mock()
    root_handler.handler_module_path = "data.plugins.demo"  # == package root
    root_handler.enabled = True
    root_handler.event_filters = [object()]

    active_plugin_md = Mock()
    active_plugin_md.activated = True
    active_plugin_md.reserved = False
    active_plugin_md.root_dir_name = "demo"
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [root_handler],
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.demo.main": active_plugin_md},
    )

    cmd_info = ("demo_cmd", "demo description", object())
    extract = Mock(return_value=cmd_info)
    monkeypatch.setattr(adapter, "_extract_command_info", extract)

    await adapter._collect_and_register_commands()

    extract.assert_called_once()
    adapter.client.add_application_command.assert_called_once()


@pytest.mark.asyncio
async def test_discord_command_sync_skips_true_orphan_handler(monkeypatch):
    """A handler owned by no plugin at all is skipped without aborting,
    and must not accidentally resolve to an unrelated plugin.
    """
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)

    orphan = Mock()
    orphan.handler_module_path = "some.unrelated.toolkit.helpers"
    orphan.enabled = True
    orphan.event_filters = [object()]

    active_plugin_md = Mock()
    active_plugin_md.activated = True
    active_plugin_md.reserved = False
    active_plugin_md.root_dir_name = "demo"
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [orphan],
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.demo.main": active_plugin_md},
    )

    extract = Mock(return_value=None)
    monkeypatch.setattr(adapter, "_extract_command_info", extract)

    await adapter._collect_and_register_commands()

    extract.assert_not_called()
    adapter.client.add_application_command.assert_not_called()
    adapter.client.sync_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_command_sync_skips_submodule_handler_of_inactive_plugin(
    monkeypatch,
):
    """A submodule handler of a deactivated plugin must not register."""
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)

    submodule_handler = Mock()
    submodule_handler.handler_module_path = "data.plugins.demo.mixin"
    submodule_handler.enabled = True
    submodule_handler.event_filters = [object()]

    inactive_plugin_md = Mock()
    inactive_plugin_md.activated = False
    inactive_plugin_md.reserved = False
    inactive_plugin_md.root_dir_name = "demo"
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [submodule_handler],
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"data.plugins.demo.main": inactive_plugin_md},
    )

    extract = Mock(return_value=None)
    monkeypatch.setattr(adapter, "_extract_command_info", extract)

    await adapter._collect_and_register_commands()

    extract.assert_not_called()
    adapter.client.add_application_command.assert_not_called()
    adapter.client.sync_commands.assert_awaited_once()
