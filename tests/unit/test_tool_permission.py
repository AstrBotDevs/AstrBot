"""Tests for per-tool permission management."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core import sp
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _PermissionGuardedTool,
)
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError

# ── helpers ──────────────────────────────────────────────────────────


def _make_context(role: str = "member", sender_id: str = "user_123"):
    """Return a mock context object suitable for tool permission checks."""

    current_role = role

    class FakeEvent:
        role = current_role
        unified_msg_origin = "aiocqhttp:GroupMessage:g1"

        def is_admin(self) -> bool:
            return role == "admin"

        def get_sender_id(self) -> str:
            return sender_id

    class FakeConfig:
        def get_config(self, umo: str | None = None):
            return {}

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

    return FakeWrapper()


def _dummy_tool(name: str = "test_tool") -> FunctionTool:
    return FunctionTool(
        name=name,
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        handler=None,
    )


async def _clear_tool_permissions() -> None:
    await sp.global_put("tool_permissions", {})


def _make_tools_service(
    tool_mgr: FunctionToolManager | None = None,
) -> ToolsService:
    """Create a minimal tools service for permission unit tests.

    Args:
        tool_mgr: Optional tool manager to attach to the service.

    Returns:
        A ToolsService backed by the selected tool manager.
    """
    return ToolsService(
        SimpleNamespace(
            provider_manager=SimpleNamespace(
                llm_tools=tool_mgr or FunctionToolManager()
            )
        )
    )


# ── _default_permission ──────────────────────────────────────────────


def test_default_permission_is_member():
    mgr = FunctionToolManager()
    assert mgr._default_permission("any_mcp_tool") == "member"


@pytest.mark.asyncio
async def test_mcp_tool_retains_admin_permission_saved_under_legacy_name(monkeypatch):
    manager = FunctionToolManager()
    client = SimpleNamespace(call_tool_with_reconnect=AsyncMock())
    tool = MCPTool(
        SimpleNamespace(name="search", description="", inputSchema={}), client, "docs"
    )
    manager.func_list.append(tool)
    monkeypatch.setattr(
        sp, "global_get", AsyncMock(return_value={"_default": {"search": "admin"}})
    )

    wrapped = manager.get_full_tool_set().get_tool("mcp__docs__search")
    assert wrapped is not None
    assert "Permission denied" in await wrapped.call(_make_context(role="member"))
    client.call_tool_with_reconnect.assert_not_awaited()


# ── _check_tool_permission ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_permission_passes_when_no_config():
    await _clear_tool_permissions()
    mgr = FunctionToolManager()
    context = _make_context(role="member")

    error = await mgr._check_tool_permission("no_such_tool", context)
    assert error is None


@pytest.mark.asyncio
async def test_check_permission_passes_for_admin_with_admin_tool():
    await sp.global_put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
    )
    try:
        mgr = FunctionToolManager()
        context = _make_context(role="admin", sender_id="admin_001")
        error = await mgr._check_tool_permission("dangerous_tool", context)
        assert error is None
    finally:
        await _clear_tool_permissions()


@pytest.mark.asyncio
async def test_check_permission_denies_member_for_admin_tool():
    await sp.global_put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
    )
    try:
        mgr = FunctionToolManager()
        context = _make_context(role="member", sender_id="user_999")
        error = await mgr._check_tool_permission("dangerous_tool", context)
        assert error is not None
        assert "dangerous_tool" in str(error)
        assert "admin" in str(error).lower()
        assert "user_999" in str(error)
    finally:
        await _clear_tool_permissions()


@pytest.mark.asyncio
async def test_check_permission_denies_when_no_event():
    await sp.global_put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
    )
    try:
        mgr = FunctionToolManager()

        class FakeWrapper:
            pass  # no .context.event

        error = await mgr._check_tool_permission("dangerous_tool", FakeWrapper())
        assert error is not None
        assert "admin" in str(error).lower()
    finally:
        await _clear_tool_permissions()


@pytest.mark.asyncio
async def test_check_permission_passes_for_member_when_configured_member():
    await sp.global_put(
        "tool_permissions",
        {"_default": {"safe_tool": "member"}},
    )
    try:
        mgr = FunctionToolManager()
        context = _make_context(role="member")
        error = await mgr._check_tool_permission("safe_tool", context)
        assert error is None
    finally:
        await _clear_tool_permissions()


# ── _PermissionGuardedTool ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_guarded_tool_delegates_handler_with_event_when_permission_passes():
    await _clear_tool_permissions()
    mgr = FunctionToolManager()

    called = False
    received_event = None

    async def handler(event, **kw):
        nonlocal called
        nonlocal received_event
        called = True
        received_event = event
        return f"ok:{event.get_sender_id()}:{kw['value']}"

    wrapped = FunctionTool(
        name="delegated",
        description="desc",
        parameters={},
        handler=handler,
    )
    guarded = _PermissionGuardedTool(wrapped, mgr)
    context = _make_context(role="member")

    result = await guarded.call(context, value="sentinel")
    assert called
    assert received_event is context.context.event
    assert result == "ok:user_123:sentinel"


@pytest.mark.asyncio
async def test_guarded_tool_blocks_when_permission_denied():
    await sp.global_put(
        "tool_permissions",
        {"_default": {"blocked_tool": "admin"}},
    )
    try:
        mgr = FunctionToolManager()
        called = False

        async def handler(ctx, **kw):
            nonlocal called
            called = True
            return "should not reach"

        wrapped = FunctionTool(
            name="blocked_tool",
            description="desc",
            parameters={},
            handler=handler,
        )
        guarded = _PermissionGuardedTool(wrapped, mgr)
        context = _make_context(role="member")

        result = await guarded.call(context)
        assert not called
        assert isinstance(result, str)
        assert "Permission denied" in result
    finally:
        await _clear_tool_permissions()


@pytest.mark.asyncio
async def test_guarded_tool_delegates_to_wrapped_call():
    await _clear_tool_permissions()
    mgr = FunctionToolManager()

    class CallableTool(FunctionTool):
        async def call(self, context, **kwargs):
            return "from call()"

    wrapped = CallableTool(
        name="has_call",
        description="desc",
        parameters={},
    )
    guarded = _PermissionGuardedTool(wrapped, mgr)
    context = _make_context()

    result = await guarded.call(context)
    assert result == "from call()"


@pytest.mark.asyncio
async def test_guarded_tool_delegates_to_wrapped_run():
    await _clear_tool_permissions()
    mgr = FunctionToolManager()

    class RunnableTool(FunctionTool):
        async def run(self, event, **kwargs):
            return f"from run(): {event.get_sender_id()} {kwargs['value']}"

    wrapped = RunnableTool(
        name="has_run",
        description="desc",
        parameters={},
    )
    guarded = _PermissionGuardedTool(wrapped, mgr)
    context = _make_context(sender_id="runner")

    result = await guarded.call(context, value="ok")
    assert result == "from run(): runner ok"


@pytest.mark.asyncio
async def test_guarded_tool_handles_async_generator_handler():
    await _clear_tool_permissions()
    mgr = FunctionToolManager()

    async def gen_handler(event, **kw):  # type: ignore[misc]
        assert event is context.context.event
        yield "A"
        yield "B"
        yield "C"

    wrapped = FunctionTool(
        name="gen_tool",
        description="desc",
        parameters={},
        handler=gen_handler,
    )
    guarded = _PermissionGuardedTool(wrapped, mgr)
    context = _make_context()

    result = await guarded.call(context)
    # should return the last yielded value
    assert result == "C"


# ── get_full_tool_set ────────────────────────────────────────────────


def test_get_full_tool_set_excludes_runtime_tools():
    """The runtime adds its tools directly to its request."""
    mgr = FunctionToolManager()
    tool_set = mgr.get_full_tool_set()

    names = {t.name for t in tool_set.tools}
    assert "astrbot_execute_shell" not in names


def test_get_full_tool_set_wraps_plugin_tools():
    mgr = FunctionToolManager()

    mgr.func_list.append(_dummy_tool("my_plugin_tool"))
    tool_set = mgr.get_full_tool_set()

    plugin_tools = [t for t in tool_set.tools if t.name == "my_plugin_tool"]
    assert plugin_tools
    assert isinstance(plugin_tools[0], _PermissionGuardedTool), (
        "plugin tools must be wrapped"
    )


# ── API: get_tool_list permission fields ──────────────────────────────


class TestGetToolListPermission:
    @pytest.mark.asyncio
    async def test_list_includes_plugin_tool_permission(self, monkeypatch):
        service = _make_tools_service()
        tool = _dummy_tool("my_plugin_tool")
        tool.handler_module_path = "plugins.test"
        monkeypatch.setattr(
            "astrbot.dashboard.services.tools_service.star_map",
            {"plugins.test": SimpleNamespace(name="test", display_name="Test")},
        )
        await sp.global_put(
            "tool_permissions",
            {"_default": {"my_plugin_tool": "admin"}},
        )
        try:
            service.tool_mgr.func_list.append(tool)
            tools = await service.get_tool_list()

            target = next(t for t in tools if t["name"] == "my_plugin_tool")
            assert target["origin"] == "plugin"
            assert target["origin_name"] == "test"
            assert target["permission"] == "admin"
            assert target["permission_configured"] is True
        finally:
            await _clear_tool_permissions()

    @pytest.mark.asyncio
    async def test_list_excludes_runtime_tools(self):
        service = _make_tools_service()
        tools = await service.get_tool_list()

        assert all(tool["name"] != "astrbot_execute_shell" for tool in tools)

    @pytest.mark.asyncio
    async def test_list_reads_permission_store_once(self, monkeypatch):
        global_get = AsyncMock(
            return_value={
                "_default": {
                    "first_tool": "admin",
                    "second_tool": "member",
                }
            }
        )
        monkeypatch.setattr(sp, "global_get", global_get)
        service = _make_tools_service()
        service.tool_mgr.func_list.extend(
            [_dummy_tool("first_tool"), _dummy_tool("second_tool")]
        )

        tools = await service.get_tool_list()

        permissions = {
            tool["name"]: tool["permission"]
            for tool in tools
            if tool["name"] in {"first_tool", "second_tool"}
        }
        assert permissions == {
            "first_tool": "admin",
            "second_tool": "member",
        }
        global_get.assert_awaited_once_with("tool_permissions", {})


# ── API: update_tool_permission ──────────────────────────────────────


class TestUpdateToolPermission:
    @pytest.mark.asyncio
    async def test_set_admin_permission(self):
        service = _make_tools_service()
        service.tool_mgr.func_list.append(_dummy_tool("target_tool"))
        await _clear_tool_permissions()

        message = await service.update_tool_permission(
            {"name": "target_tool", "permission": "admin"}
        )
        assert "target_tool" in message

        stored = await sp.global_get("tool_permissions", {})
        assert stored["_default"]["target_tool"] == "admin"

    @pytest.mark.asyncio
    async def test_reject_runtime_tool(self):
        service = _make_tools_service()

        with pytest.raises(ToolsServiceError, match="not found"):
            await service.update_tool_permission(
                {"name": "astrbot_execute_shell", "permission": "admin"}
            )

    @pytest.mark.asyncio
    async def test_reject_unknown_tool(self):
        service = _make_tools_service()

        with pytest.raises(ToolsServiceError, match="not found"):
            await service.update_tool_permission(
                {"name": "ghost_tool", "permission": "admin"}
            )

    @pytest.mark.asyncio
    async def test_reject_invalid_permission_value(self):
        service = _make_tools_service()
        service.tool_mgr.func_list.append(_dummy_tool("target_tool"))

        with pytest.raises(ToolsServiceError, match="admin or member"):
            await service.update_tool_permission(
                {"name": "target_tool", "permission": "everyone"}
            )
