from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.pipeline import context_utils
from astrbot.core.pipeline.process_stage.method import star_request
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star_handler import EventType
from astrbot.dashboard.services.plugin_service import PluginService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_filter", "category"),
    [
        (CommandFilter("test"), "command"),
        (CommandGroupFilter("test"), "command"),
        (RegexFilter("test"), "command"),
        (None, "listener"),
    ],
)
async def test_message_handler_trace_category(monkeypatch, event_filter, category):
    handler = SimpleNamespace(
        handler=AsyncMock(return_value=None),
        handler_name="test_handler",
        handler_full_name="test_plugin.test_handler",
        handler_module_path="test_plugin",
        event_type=EventType.AdapterMessageEvent,
        event_filters=[event_filter] if event_filter else [],
        extras_configs={},
    )
    monkeypatch.setitem(
        star_request.star_map,
        "test_plugin",
        SimpleNamespace(name="test_plugin", display_name="Test Plugin"),
    )
    extras = {"activated_handlers": [handler], "handlers_parsed_params": {}}
    event = MagicMock()
    event._extras = extras
    event.get_extra.side_effect = extras.get
    event.set_extra.side_effect = extras.__setitem__
    event.is_stopped.return_value = False

    async for _ in star_request.StarRequestSubStage().process(event):
        pass

    records = event.trace.record.call_args_list
    assert [record.args[0] for record in records] == ["handler_start", "handler_end"]
    for record in records:
        assert record.kwargs["handler_category"] == category
        assert record.kwargs["handler_type"] == "AdapterMessageEvent"
        assert record.kwargs["plugin_display_name"] == "Test Plugin"
    assert "_trace_response_source" not in extras


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hook_type", "category"),
    [
        (EventType.OnLLMRequestEvent, "hook"),
        (EventType.OnCallingFuncToolEvent, "llm_tool"),
    ],
)
@pytest.mark.parametrize("fails", [False, True])
async def test_event_hook_trace_category(monkeypatch, hook_type, category, fails):
    handler = SimpleNamespace(
        handler=AsyncMock(side_effect=ValueError("test failure") if fails else None),
        handler_name="test_hook",
        handler_full_name="test_plugin.test_hook",
        handler_module_path="test_plugin",
        event_type=hook_type,
    )
    monkeypatch.setattr(
        context_utils.star_handlers_registry,
        "get_handlers_by_event_type",
        MagicMock(return_value=[handler]),
    )
    monkeypatch.setitem(
        context_utils.star_map,
        "test_plugin",
        SimpleNamespace(name="test_plugin", display_name="Test Plugin"),
    )
    extras = {"_trace_response_source": "agent"}
    event = MagicMock()
    event._extras = extras
    event.get_extra.side_effect = extras.get
    event.set_extra.side_effect = extras.__setitem__
    event.is_stopped.return_value = False

    assert await context_utils.call_event_hook(event, hook_type) is False

    records = event.trace.record.call_args_list
    assert [record.args[0] for record in records] == ["handler_start", "handler_end"]
    for record in records:
        assert record.kwargs["handler_category"] == category
        assert record.kwargs["handler_type"] == hook_type.name
    assert records[-1].kwargs["status"] == ("error" if fails else "success")
    assert extras["_trace_response_source"] == "agent"


@pytest.mark.asyncio
async def test_nested_command_details_preserve_handler_identity(monkeypatch):
    handlers = {}
    group = CommandGroupFilter("admin")
    for command in ("first", "second"):
        event_filter = CommandFilter(command, parent_command_names=["admin"])
        handler = SimpleNamespace(
            handler_name=f"handle_{command}",
            handler_full_name=f"test_plugin.handle_{command}",
            event_type=EventType.AdapterMessageEvent,
            event_filters=[event_filter],
            desc=f"Description for {command}",
        )
        event_filter.handler_md = handler
        handlers[handler.handler_full_name] = handler
        group.add_sub_command_filter(event_filter)
    monkeypatch.setattr(
        context_utils.star_handlers_registry, "star_handlers_map", handlers
    )
    service = PluginService(MagicMock(), MagicMock())
    components = await service.get_plugin_handler_components(list(handlers))

    assert len(components) == 1
    assert components[0]["name"] == "admin"
    for command, child in zip(("first", "second"), components[0]["subcommands"]):
        assert child["handler_full_name"] == f"test_plugin.handle_{command}"
        assert child["handler_name"] == f"handle_{command}"
        assert child["description"] == f"Description for {command}"

    group_component = service._build_command_group_component(group)
    for command, child in zip(("first", "second"), group_component["subcommands"]):
        assert child["handler_full_name"] == f"test_plugin.handle_{command}"
        assert child["description"] == f"Description for {command}"
