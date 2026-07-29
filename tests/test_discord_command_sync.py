import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from tests.fixtures.mocks.discord import (
    MockDiscordBuilder,
    mock_discord_modules,  # noqa: F401
)


class DiscordSyncError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class FakeSlashCommand:
    def __init__(self, *, name, description, func, options, parent=None):
        self.name = name
        self.description = description
        self.callback = func
        self.options = options
        self.parent = parent


class FakeSlashCommandGroup:
    def __init__(self, *, name, description, guild_ids=None, parent=None):
        self.name = name
        self.description = description
        self.guild_ids = guild_ids
        self.parent = parent
        self.subcommands = []

    def add_command(self, command):
        self.subcommands.append(command)


def _command_filter(name, description, parent_names):
    command_filter = CommandFilter(name, parent_command_names=parent_names)
    command_filter.handler_md = SimpleNamespace(desc=description, enabled=True)
    command_filter.handler_params = {}
    return command_filter


def _build_adapter(monkeypatch: pytest.MonkeyPatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )

    monkeypatch.setattr(discord_platform_adapter, "star_handlers_registry", [])
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


def _patch_slash_command_types(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "SlashCommand",
        FakeSlashCommand,
    )
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "SlashCommandGroup",
        FakeSlashCommandGroup,
    )
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "Option",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )


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
async def test_discord_registers_command_group_as_one_slash_command(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)
    _patch_slash_command_types(monkeypatch)

    root = CommandGroupFilter("pixiv")
    search = _command_filter("search", "Search illustrations", ["pixiv"])
    user_group = CommandGroupFilter("user", parent_group=root)
    detail = _command_filter("detail", "Show user details", ["pixiv user"])
    user_group.add_sub_command_filter(detail)
    root.add_sub_command_filter(search)
    root.add_sub_command_filter(user_group)

    root_metadata = SimpleNamespace(
        desc="Pixiv commands",
        enabled=True,
        handler_module_path="pixiv_plugin",
        event_filters=[root],
    )
    search_metadata = SimpleNamespace(
        desc="Search illustrations",
        enabled=True,
        handler_module_path="pixiv_plugin",
        event_filters=[search],
    )
    user_group_metadata = SimpleNamespace(
        desc="User commands",
        enabled=True,
        handler_module_path="pixiv_plugin",
        event_filters=[user_group],
    )
    detail_metadata = SimpleNamespace(
        desc="Show user details",
        enabled=True,
        handler_module_path="pixiv_plugin",
        event_filters=[detail],
    )
    search.handler_md = search_metadata
    detail.handler_md = detail_metadata
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_handlers_registry",
        [root_metadata, search_metadata, user_group_metadata, detail_metadata],
    )
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"pixiv_plugin": SimpleNamespace(activated=True)},
    )

    await adapter._collect_and_register_commands()

    adapter.client.add_application_command.assert_called_once()
    slash_root = adapter.client.add_application_command.call_args.args[0]
    assert slash_root.name == "pixiv"
    assert [command.name for command in slash_root.subcommands] == ["search", "user"]
    assert [command.name for command in slash_root.subcommands[1].subcommands] == [
        "detail"
    ]


@pytest.mark.asyncio
async def test_discord_group_callback_rebuilds_full_command_path(monkeypatch):
    adapter = _build_adapter(monkeypatch)
    _patch_slash_command_types(monkeypatch)
    adapter.bot_self_id = "bot-id"
    adapter.handle_msg = AsyncMock()

    root = CommandGroupFilter("pixiv")
    user_group = CommandGroupFilter("user", parent_group=root)
    detail = _command_filter("detail", "Show user details", ["pixiv user"])
    user_group.add_sub_command_filter(detail)
    root.add_sub_command_filter(user_group)
    root_metadata = SimpleNamespace(desc="Pixiv commands")

    slash_root = adapter._create_slash_command_group(root, root_metadata)
    detail_command = slash_root.subcommands[0].subcommands[0]
    context = SimpleNamespace(
        defer=AsyncMock(),
        followup=object(),
        channel=SimpleNamespace(id=123),
        channel_id=123,
        guild_id=456,
        author=SimpleNamespace(id=789, display_name="tester"),
        interaction=SimpleNamespace(id=999),
    )

    await detail_command.callback(context, "42")

    message = adapter.handle_msg.await_args.args[0]
    assert message.message_str == "pixiv user detail 42"


def test_discord_skips_command_groups_deeper_than_one_level(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)
    _patch_slash_command_types(monkeypatch)
    warning = Mock()
    monkeypatch.setattr(discord_platform_adapter.logger, "warning", warning)

    root = CommandGroupFilter("pixiv")
    random_group = CommandGroupFilter("random", parent_group=root)
    status = _command_filter("status", "Show queue status", ["pixiv random"])
    ranking_group = CommandGroupFilter("ranking", parent_group=random_group)
    ranking_add = _command_filter(
        "add",
        "Add ranking source",
        ["pixiv random ranking"],
    )
    ranking_group.add_sub_command_filter(ranking_add)
    random_group.add_sub_command_filter(status)
    random_group.add_sub_command_filter(ranking_group)
    root.add_sub_command_filter(random_group)

    slash_root = adapter._create_slash_command_group(
        root,
        SimpleNamespace(desc="Pixiv commands"),
    )

    assert [command.name for command in slash_root.subcommands] == ["random"]
    assert [command.name for command in slash_root.subcommands[0].subcommands] == [
        "status"
    ]
    assert any(
        "deeper than one level" in call.args[0] for call in warning.call_args_list
    )
