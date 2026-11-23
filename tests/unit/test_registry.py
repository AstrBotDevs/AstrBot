"""Registration, selection, schemas, and permissions through the current manager."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.computer.computer_tool_provider import (
    get_all_tools,
)
from astrbot.core.provider import func_tool_manager as registry
from astrbot.core.provider.func_tool_manager import FunctionToolManager


@pytest.fixture
def manager():
    """Each registry belongs to the test rather than global decorator state."""
    return FunctionToolManager()


@pytest.fixture
def preferences(monkeypatch):
    """Replace only the preference persistence boundary."""
    state = {"inactivated_llm_tools": [], "tool_permissions": {}}

    async def get(scope, scope_id, key, default):
        assert (scope, scope_id) == ("global", "global")
        return deepcopy(state.get(key, default))

    async def put(scope, scope_id, key, value):
        assert (scope, scope_id) == ("global", "global")
        state[key] = deepcopy(value)

    async def global_get(key, default):
        return deepcopy(state.get(key, default))

    boundary = SimpleNamespace(
        get_async=AsyncMock(side_effect=get),
        put_async=AsyncMock(side_effect=put),
        global_get=AsyncMock(side_effect=global_get),
    )
    monkeypatch.setattr(registry, "sp", boundary)
    return state, boundary


def test_registration_round_trip_replacement_and_removal(manager):
    first, second = AsyncMock(return_value="first"), AsyncMock(return_value="second")
    manager.add_func("probe", [{"name": "value", "type": "string"}], "first", first)
    original = manager.get_func("probe")
    assert original is not None and original.handler is first
    manager.add_func("probe", [], "replacement", second)
    assert len(manager.func_list) == 1
    replacement = manager.get_func("probe")
    assert replacement is not original
    assert replacement.handler is second and replacement.description == "replacement"
    manager.remove_func("missing")
    assert manager.get_func("probe") is replacement
    manager.remove_func("probe")
    assert manager.empty() and manager.get_func("probe") is None


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "enum": ["a", "b"]},
        {
            "type": "array",
            "items": {"type": "object", "properties": {"value": {"type": "integer"}}},
        },
        {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
    ],
)
def test_registration_copies_nested_parameter_specs(manager, schema):
    args = [{"name": "value", **deepcopy(schema)}]
    original = deepcopy(args)
    tool = manager.spec_to_func("probe", args, "description", AsyncMock())
    assert tool.parameters == {"type": "object", "properties": {"value": schema}}
    assert args == original
    args[0].clear()
    assert tool.parameters["properties"]["value"] == schema


@pytest.mark.parametrize(
    "first_active,second_active,winner",
    [(True, True, 1), (False, True, 1), (True, False, 0), (False, False, 1)],
)
def test_selection_and_executable_set_agree_on_name_conflicts(
    manager, first_active, second_active, winner
):
    tools = [
        FunctionTool(name="shared", description="first", active=first_active),
        FunctionTool(name="shared", description="second", active=second_active),
    ]
    manager.func_list = tools
    assert manager.get_func("shared") is tools[winner]
    selected = manager.get_full_tool_set().tools
    assert len(selected) == 1
    assert selected[0].description == tools[winner].description
    assert selected[0].active is tools[winner].active


def test_native_registration_catalog_does_not_pollute_plugin_registry(manager):
    native = get_all_tools()
    assert native and all(not tool.active for tool in native)
    assert manager.empty()
    assert manager.get_full_tool_set().tools == []


@pytest.mark.parametrize("format_name", ["openai", "anthropic"])
def test_provider_schema_contains_only_active_registered_tools(manager, format_name):
    manager.func_list = [
        FunctionTool(
            name="enabled",
            description="enabled",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        ),
        FunctionTool(name="disabled", description="disabled", active=False),
    ]
    schema = getattr(manager, f"get_func_desc_{format_name}_style")()
    assert len(schema) == 1
    entry = schema[0]["function"] if format_name == "openai" else schema[0]
    assert entry["name"] == "enabled"
    key = "parameters" if format_name == "openai" else "input_schema"
    assert entry[key]["properties"]["text"]["type"] == "string"


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [("admin", True), ("member", False)])
async def test_permission_guard_checks_before_calling_registered_handler(
    manager, preferences, role, allowed
):
    state, boundary = preferences
    state["tool_permissions"] = {"_default": {"probe": "admin"}}
    handler = AsyncMock(return_value="handled")
    manager.add_func("probe", [], "guarded", handler)
    event = SimpleNamespace(
        role=role, get_extra=lambda _: None, get_sender_id=lambda: "caller"
    )
    context = ContextWrapper(context=SimpleNamespace(event=event))
    guarded = manager.get_full_tool_set().tools[0]
    result = await guarded.call(context, value="input")
    boundary.global_get.assert_awaited_once_with("tool_permissions", {})
    if allowed:
        assert result == "handled"
        handler.assert_awaited_once_with(event, value="input")
    else:
        assert "Permission denied" in result and "probe" in result
        handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_deactivation_and_reactivation_persist_once_and_preserve_tool(
    manager, preferences
):
    state, boundary = preferences
    manager.add_func("probe", [], "description", AsyncMock())
    tool = manager.get_func("probe")
    assert await manager.deactivate_llm_tool_async("probe") is True
    assert not tool.active and state["inactivated_llm_tools"] == ["probe"]
    assert await manager.deactivate_llm_tool_async("probe") is True
    assert boundary.put_async.await_count == 1
    assert await manager.activate_llm_tool_async("probe", {}) is True
    assert tool.active and state["inactivated_llm_tools"] == []
    assert manager.get_func("probe") is tool
    assert boundary.put_async.await_count == 2


@pytest.mark.asyncio
async def test_unknown_activation_has_no_persistence_effect(manager, preferences):
    _, boundary = preferences
    assert await manager.deactivate_llm_tool_async("missing") is False
    assert await manager.activate_llm_tool_async("missing", {}) is False
    boundary.get_async.assert_not_awaited()
    boundary.put_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_plugin_cannot_reactivate_its_tool(manager, preferences):
    _, boundary = preferences
    tool = FunctionTool(
        name="probe",
        description="description",
        active=False,
        handler_module_path="plugin.main",
    )
    manager.func_list = [tool]
    with pytest.raises(ValueError, match="已被禁用"):
        await manager.activate_llm_tool_async(
            "probe", {"plugin.main": SimpleNamespace(activated=False, name="plugin")}
        )
    assert not tool.active
    boundary.put_async.assert_not_awaited()
