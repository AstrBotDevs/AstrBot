import asyncio
import enum
import inspect
from types import SimpleNamespace
from typing import Annotated, Literal
from unittest.mock import AsyncMock, Mock

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
    from astrbot.core.star.star import PluginRegistry
    from astrbot.core.star.star_handler import HandlerRegistry

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
    plugins = PluginRegistry()
    adapter.bind_runtime_registries(HandlerRegistry(plugins), plugins)
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
async def test_discord_registers_native_command_groups_and_routes_subcommands(
    monkeypatch,
):
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.filter.command_group import CommandGroupFilter
    from astrbot.core.star.star import StarMetadata
    from astrbot.core.star.star_handler import EventType, StarHandlerMetadata

    adapter = _build_adapter(monkeypatch)
    adapter.bot_self_id = "bot"
    adapter.handle_msg = AsyncMock()

    class FakeSlashCommand:
        def __init__(self, **kwargs):
            self.name = kwargs["name"]
            self.func = kwargs["func"]
            self.options = kwargs["options"]
            self.parent = kwargs.get("parent")

    class FakeSlashCommandGroup:
        def __init__(self, **kwargs):
            self.name = kwargs["name"]
            self.parent = kwargs.get("parent")
            self.subcommands = []

        def add_command(self, command):
            self.subcommands.append(command)

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
        lambda input_type=str, **kwargs: {"input_type": input_type, **kwargs},
    )

    group_filter = CommandGroupFilter("provider")

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_provider",
        "provider",
        "plugin.demo",
        group_handler,
        [group_filter],
        desc="Manage providers",
    )

    set_filter = CommandGroupFilter("set", parent_group=group_filter)
    group_filter.add_sub_command_filter(set_filter)

    async def llm(self, event, index: int) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_provider_llm",
        "provider_llm",
        "plugin.demo",
        llm,
        [],
        desc="Switch LLM provider",
        extras_configs={"sub_command": True},
    )
    child_filter = CommandFilter(
        "llm",
        parent_command_names=["provider set"],
    )
    child_filter.init_handler_md(child_md)
    child_md.event_filters.append(child_filter)
    set_filter.add_sub_command_filter(child_filter)

    adapter.get_plugin_registry().publish(
        StarMetadata(
            name="Demo",
            module_path="plugin.demo",
            activated=True,
        ),
    )
    adapter.get_handler_registry().append(group_md)
    adapter.get_handler_registry().append(child_md)

    await adapter._collect_and_register_commands()
    first_group = adapter.client.add_application_command.call_args.args[0]
    await adapter.refresh_registered_commands()

    group = adapter.client.add_application_command.call_args.args[0]
    adapter.client.remove_application_command.assert_called_once_with(first_group)
    assert adapter.client.sync_commands.await_count == 2
    assert group.name == "provider"
    assert [command.name for command in group.subcommands] == ["set"]
    set_group = group.subcommands[0]
    assert [command.name for command in set_group.subcommands] == ["llm"]
    assert set_group.subcommands[0].options == [
        {
            "name": "index",
            "description": "index (int)",
            "input_type": int,
            "required": True,
        }
    ]

    context = SimpleNamespace(
        defer=AsyncMock(),
        followup=object(),
        channel=None,
        guild_id=None,
        channel_id="channel",
        author=SimpleNamespace(id="user", display_name="User"),
        interaction=SimpleNamespace(id="interaction"),
    )
    await set_group.subcommands[0].func(context, "1")

    message = adapter.handle_msg.await_args.args[0]
    assert message.message_str == "provider set llm -- '1'"


@pytest.mark.asyncio
async def test_discord_native_options_preserve_orbit_argument_values(monkeypatch):
    from astrbot.api.event.filter import option
    from astrbot.core.command.binder import CommandBinder
    from astrbot.core.command.lexer import parse_arguments
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.star import StarMetadata
    from astrbot.core.star.star_handler import EventType, StarHandlerMetadata

    adapter = _build_adapter(monkeypatch)
    adapter.bot_self_id = "bot"
    adapter.handle_msg = AsyncMock()

    class Mode(enum.Enum):
        FAST = "fast"
        SAFE = "safe"

    async def run(
        self,
        event,
        target: str,
        count: int,
        ratio: float = 1.0,
        mode: Literal["fast", "safe"] = "safe",
        strategy: Mode = Mode.SAFE,
        verbose: Annotated[bool, option("--verbose", "-v")] = False,
    ) -> None: ...

    handler_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_run",
        "run",
        "plugin.demo",
        run,
        [],
        desc="Run a native command",
    )
    command_filter = CommandFilter("run", alias={"execute"})
    command_filter.init_handler_md(handler_md)
    handler_md.event_filters.append(command_filter)

    adapter.get_plugin_registry().publish(
        StarMetadata(
            name="Demo",
            module_path="plugin.demo",
            activated=True,
        ),
    )
    adapter.get_handler_registry().append(handler_md)
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "SlashCommand",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "Option",
        lambda input_type=str, **kwargs: {"input_type": input_type, **kwargs},
    )

    await adapter._collect_and_register_commands()

    registered = [
        call.args[0] for call in adapter.client.add_application_command.call_args_list
    ]
    assert [command.name for command in registered] == ["run", "execute"]
    slash_command = registered[0]
    assert tuple(inspect.signature(slash_command.func).parameters) == (
        "ctx",
        "target",
        "count",
        "ratio",
        "mode",
        "strategy",
        "verbose",
    )
    assert [item["name"] for item in slash_command.options] == [
        "target",
        "count",
        "ratio",
        "mode",
        "strategy",
        "verbose",
    ]
    assert slash_command.options[0]["required"] is True
    assert slash_command.options[1]["input_type"] is int
    assert slash_command.options[2]["input_type"] is float
    assert slash_command.options[3]["choices"] == ["fast", "safe"]
    assert slash_command.options[4]["choices"] == ["fast", "safe"]
    assert slash_command.options[5]["input_type"] is bool

    context = SimpleNamespace(
        defer=AsyncMock(),
        followup=object(),
        channel=None,
        guild_id=None,
        channel_id="channel",
        author=SimpleNamespace(id="user", display_name="User"),
        interaction=SimpleNamespace(id="interaction"),
    )
    await slash_command.func(
        context,
        target="a'b $HOME -x",
        count=2,
        mode="fast",
        strategy="fast",
        verbose=True,
    )

    message = adapter.handle_msg.await_args.args[0]
    assert "$HOME" in message.message_str
    invocation = parse_arguments(message.message_str.removeprefix("run "))
    values = dict(CommandBinder().bind(command_filter.schema, invocation).values)
    assert values == {
        "target": "a'b $HOME -x",
        "count": 2,
        "ratio": 1.0,
        "mode": "fast",
        "strategy": Mode.FAST,
        "verbose": True,
    }
