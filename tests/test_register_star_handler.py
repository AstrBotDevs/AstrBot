"""Decorators register real handler metadata without leaking global registries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.register import star_handler as registration
from astrbot.core.star.star_handler import EventType, StarHandlerRegistry


@pytest.fixture
def registry(monkeypatch):
    registry = StarHandlerRegistry()
    monkeypatch.setattr(registration, "star_handlers_registry", registry)
    return registry


@pytest.mark.parametrize(
    ("decorator", "event_type"),
    [
        ("register_on_astrbot_loaded", EventType.OnAstrBotLoadedEvent),
        ("register_on_platform_loaded", EventType.OnPlatformLoadedEvent),
        ("register_on_plugin_loaded", EventType.OnPluginLoadedEvent),
        ("register_on_plugin_unloaded", EventType.OnPluginUnloadedEvent),
        ("register_on_plugin_error", EventType.OnPluginErrorEvent),
        ("register_on_waiting_llm_request", EventType.OnWaitingLLMRequestEvent),
        ("register_on_llm_request", EventType.OnLLMRequestEvent),
        ("register_on_llm_response", EventType.OnLLMResponseEvent),
        ("register_on_agent_begin", EventType.OnAgentBeginEvent),
        ("register_on_agent_done", EventType.OnAgentDoneEvent),
        ("register_on_using_llm_tool", EventType.OnUsingLLMToolEvent),
        ("register_on_llm_tool_respond", EventType.OnLLMToolRespondEvent),
        ("register_on_decorating_result", EventType.OnDecoratingResultEvent),
        ("register_after_message_sent", EventType.OnAfterMessageSentEvent),
    ],
)
def test_lifecycle_decorator_preserves_function_and_event_contract(
    registry, decorator, event_type
):
    async def hook(*args):
        return args

    result = getattr(registration, decorator)(priority=7, desc="Lifecycle hook")(hook)
    assert result is hook
    metadata = registry.get_handler_by_full_name(
        registration.get_handler_full_name(hook)
    )
    assert metadata.handler is hook
    assert metadata.event_type is event_type
    assert metadata.desc == "Lifecycle hook"
    assert metadata.extras_configs == {"priority": 7}
    assert len(registry) == 1


def test_stacked_filters_share_one_handler(registry):
    async def command(self, event, enabled: bool = False):
        """Toggle a setting."""

    assert registration.register_command("toggle", alias={"t"})(command) is command
    registration.register_permission_type(PermissionType.ADMIN)(command)
    registration.register_regex(r"^toggle")(command)
    metadata = next(iter(registry))
    assert len(registry) == 1
    assert metadata.desc == "Toggle a setting."
    assert [type(item) for item in metadata.event_filters] == [
        CommandFilter,
        PermissionTypeFilter,
        RegexFilter,
    ]
    command_filter = metadata.event_filters[0]
    assert command_filter.command_name == "toggle"
    assert command_filter.alias == {"t"}
    assert command_filter.get_handler_md() is metadata
    assert command_filter.validate_and_convert_params(
        ["false"], command_filter.handler_params
    ) == {"enabled": False}


def test_metadata_can_be_prepared_without_registering(registry):
    async def handler(event):
        """Original description."""

    metadata = registration.get_handler_or_create(
        handler, EventType.AdapterMessageEvent, dont_add=True, desc="Override"
    )
    assert len(registry) == 0
    assert metadata.desc == "Override"
    assert metadata.handler is handler
    registry.append(metadata)
    assert (
        registration.get_handler_or_create(handler, EventType.AdapterMessageEvent)
        is metadata
    )
    assert len(registry) == 1


def test_tool_decorator_preserves_schema_and_calling_hook(registry, monkeypatch):
    manager = SimpleNamespace(add_func=Mock())
    monkeypatch.setattr(registration, "llm_tools", manager)

    async def lookup(event, query: str, count: int):
        """Search local records.

        Args:
            query(string): Search text.
            count(int): Maximum results.
        """

    assert registration.register_llm_tool(name="local_lookup")(lookup) is lookup
    metadata = next(iter(registry))
    assert metadata.event_type is EventType.OnCallingFuncToolEvent
    manager.add_func.assert_called_once()
    name, arguments, description, handler = manager.add_func.call_args.args
    assert (name, description, handler) == (
        "local_lookup",
        "Search local records.",
        lookup,
    )
    assert arguments == [
        {"type": "string", "name": "query", "description": "Search text."},
        {"type": "number", "name": "count", "description": "Maximum results."},
    ]
