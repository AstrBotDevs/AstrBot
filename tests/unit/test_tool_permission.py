"""Regression coverage for the unified function-tool authorization boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import mcp
import pytest

from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.auth.models import Role
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.plugin_context import AuthorizationCapability
from astrbot.core.star.star import StarMetadata
from astrbot.core.tools.function_tool_manager import FunctionToolManager


def _tool(name: str = "plugin_tool") -> FunctionTool:
    return FunctionTool(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(return_value="ok"),
    )


def _mcp_tool(*, read_only_hint: bool | None) -> MCPTool:
    from mcp.types import Tool, ToolAnnotations

    return MCPTool(
        Tool(
            name="docs_query",
            description="Query documentation",
            inputSchema={"type": "object", "properties": {}},
            annotations=ToolAnnotations(readOnlyHint=read_only_hint),
        ),
        SimpleNamespace(),
        "context7",
    )


def _run_context(*, authorization=None, complete=True):
    event = SimpleNamespace(
        subject=SimpleNamespace(id="im:test:bot:user", authenticated=True),
        resource=SimpleNamespace(config_id="default"),
        auth_context=SimpleNamespace(),
    )
    if not complete:
        event.auth_context = None
    runtime = SimpleNamespace(authorization=authorization)
    return ContextWrapper(context=SimpleNamespace(event=event, context=runtime))


def test_get_full_tool_set_returns_original_tools():
    manager = FunctionToolManager()
    tool = _tool()
    manager.func_list = [tool]

    assert manager.get_full_tool_set().get_tool(tool.name) is tool


def test_unclaimed_plugin_tools_have_no_implicit_authorization_action():
    assert FunctionToolExecutor._required_actions(_tool()) == ()


def test_mcp_read_only_hint_uses_read_permission_for_sdk2_annotations():
    assert FunctionToolExecutor._required_actions(_mcp_tool(read_only_hint=True)) == (
        "tool.mcp_read",
    )


def test_mcp_tools_without_read_only_hint_require_write_permission():
    assert FunctionToolExecutor._required_actions(_mcp_tool(read_only_hint=None)) == (
        "tool.mcp_write",
    )


@pytest.mark.asyncio
async def test_execution_denies_when_authorization_context_is_missing():
    tool = _tool()
    run_context = _run_context(authorization=None)

    results = [item async for item in FunctionToolExecutor.execute(tool, run_context)]

    assert len(results) == 1
    assert isinstance(results[0], mcp.types.CallToolResult)
    assert "Permission denied" in results[0].content[0].text
    tool.handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_checks_required_action_before_handler():
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=False))
    )
    tool = _tool()
    tool.required_actions = ("session.read",)
    run_context = _run_context(authorization=authorization)

    results = [item async for item in FunctionToolExecutor.execute(tool, run_context)]

    assert "Permission denied" in results[0].content[0].text
    authorization.authorize.assert_awaited_once()
    tool.handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_calls_handler_after_authorization():
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )
    tool = _tool()
    tool.required_actions = ("session.read",)
    run_context = _run_context(authorization=authorization)

    results = [item async for item in FunctionToolExecutor.execute(tool, run_context)]

    assert len(results) == 1
    assert results[0].content[0].text == "ok"
    tool.handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_execution_denies_an_unclaimed_tool_before_its_handler():
    authorization = SimpleNamespace(authorize=AsyncMock())
    tool = _tool()

    results = [
        item
        async for item in FunctionToolExecutor.execute(
            tool,
            _run_context(authorization=authorization),
        )
    ]

    assert "not declared" in results[0].content[0].text
    authorization.authorize.assert_not_awaited()
    tool.handler.assert_not_awaited()


def test_plugin_local_tool_actions_must_be_declared_in_plugin_metadata():
    metadata = StarMetadata(
        name="weather",
        author="Example",
        authorization_actions=frozenset({"plugin:example/weather:lookup"}),
    )

    assert PluginCatalog._resolve_plugin_tool_actions(
        metadata,
        ("plugin:lookup",),
    ) == ("plugin:example/weather:lookup",)
    with pytest.raises(ValueError, match="not declared"):
        PluginCatalog._resolve_plugin_tool_actions(metadata, ("plugin:write",))


@pytest.mark.asyncio
async def test_plugin_authz_cannot_request_core_actions_or_manage_bindings():
    authorization = SimpleNamespace(authorize=AsyncMock())
    capability = AuthorizationCapability(authorization).for_plugin(
        "example/weather",
        frozenset({"plugin:example/weather:lookup"}),
    )
    event = SimpleNamespace()

    with pytest.raises(PermissionError, match="not declared"):
        await capability.authorize(event, "session.read")
    with pytest.raises(PermissionError, match="not declared"):
        await capability.authorize(event, "plugin:other:lookup")
    with pytest.raises(PermissionError, match="cannot manage"):
        await capability.list_bindings(event)
    with pytest.raises(PermissionError, match="cannot manage"):
        await capability.grant_session_admin(event, "target")
    with pytest.raises(PermissionError, match="cannot manage"):
        await capability.revoke_session_admin(event, "target")
    authorization.authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_owner_binding_list_is_limited_to_current_session():
    current_resource = SimpleNamespace(type="session", id="session:v1:default:current")
    bindings = [
        SimpleNamespace(scope_type="session", scope_id=current_resource.id),
        SimpleNamespace(scope_type="session", scope_id="session:v1:default:other"),
        SimpleNamespace(scope_type="instance", scope_id="default"),
    ]
    authorization = SimpleNamespace(
        authorize=AsyncMock(
            return_value=SimpleNamespace(
                allowed=True,
                effective_role=Role.SESSION_OWNER,
            )
        ),
        list_bindings=AsyncMock(return_value=bindings),
    )
    event = SimpleNamespace(
        subject=SimpleNamespace(id="im:napcat:bot:user", authenticated=True),
        resource=current_resource,
        auth_context=SimpleNamespace(config_id="default"),
    )

    visible = await AuthorizationCapability(authorization).list_bindings(event)

    assert visible == [bindings[0]]
    authorization.authorize.assert_awaited_once_with(
        event.subject,
        "identity.manage",
        event.resource,
        event.auth_context,
    )
    authorization.list_bindings.assert_awaited_once_with(config_id="default")
