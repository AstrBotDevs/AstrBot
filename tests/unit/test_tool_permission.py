"""Tests for per-tool permission management."""

from unittest.mock import MagicMock

import pytest

from astrbot.core import sp
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _PermissionGuardedTool,
)
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError

# ── helpers ──────────────────────────────────────────────────────────


def _make_context(role: str = "member", sender_id: str = "user_123"):
    """Return a mock context object suitable for tool permission checks."""

    class FakeEvent:
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


def _clear_tool_permissions() -> None:
    sp.put("tool_permissions", {}, scope="global", scope_id="global")


def _make_tools_service(
    tool_mgr: FunctionToolManager | None = None,
) -> ToolsService:
    """Create a minimal tools service for permission unit tests.

    Args:
        tool_mgr: Optional tool manager to attach to the service.

    Returns:
        A ToolsService with mocked lifecycle config access.
    """
    service = ToolsService.__new__(ToolsService)
    service.core_lifecycle = MagicMock()
    service.core_lifecycle.astrbot_config_mgr = MagicMock()
    service.core_lifecycle.astrbot_config_mgr.get_conf_list.return_value = []
    service.core_lifecycle.astrbot_config_mgr.confs = {}
    service.tool_mgr = tool_mgr or FunctionToolManager()
    return service


# ── _default_permission ──────────────────────────────────────────────


def test_default_permission_is_member():
    mgr = FunctionToolManager()
    assert mgr._default_permission("any_mcp_tool") == "member"


# ── _check_tool_permission ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_permission_passes_when_no_config():
    _clear_tool_permissions()
    mgr = FunctionToolManager()
    context = _make_context(role="member")

    error = mgr._check_tool_permission("no_such_tool", context)
    assert error is None


@pytest.mark.asyncio
async def test_check_permission_passes_for_admin_with_admin_tool():
    sp.put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
        scope="global",
        scope_id="global",
    )
    try:
        mgr = FunctionToolManager()
        context = _make_context(role="admin", sender_id="admin_001")
        error = mgr._check_tool_permission("dangerous_tool", context)
        assert error is None
    finally:
        _clear_tool_permissions()


@pytest.mark.asyncio
async def test_check_permission_denies_member_for_admin_tool():
    sp.put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
        scope="global",
        scope_id="global",
    )
    try:
        mgr = FunctionToolManager()
        context = _make_context(role="member", sender_id="user_999")
        error = mgr._check_tool_permission("dangerous_tool", context)
        assert error is not None
        assert "dangerous_tool" in str(error)
        assert "admin" in str(error).lower()
        assert "user_999" in str(error)
    finally:
        _clear_tool_permissions()


@pytest.mark.asyncio
async def test_check_permission_denies_when_no_event():
    sp.put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
        scope="global",
        scope_id="global",
    )
    try:
        mgr = FunctionToolManager()

        class FakeWrapper:
            pass  # no .context.event

        error = mgr._check_tool_permission("dangerous_tool", FakeWrapper())
        assert error is not None
        assert "admin" in str(error).lower()
    finally:
        _clear_tool_permissions()


@pytest.mark.asyncio
async def test_check_permission_passes_for_member_when_configured_member():
    sp.put(
        "tool_permissions",
        {"_default": {"safe_tool": "member"}},
        scope="global",
        scope_id="global",
    )
    try:
        mgr = FunctionToolManager()
        context = _make_context(role="member")
        error = mgr._check_tool_permission("safe_tool", context)
        assert error is None
    finally:
        _clear_tool_permissions()


# ── _PermissionGuardedTool ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_guarded_tool_delegates_when_permission_passes():
    _clear_tool_permissions()
    mgr = FunctionToolManager()

    called = False

    async def handler(ctx, **kw):
        nonlocal called
        called = True
        return "ok"

    wrapped = FunctionTool(
        name="delegated",
        description="desc",
        parameters={},
        handler=handler,
    )
    guarded = _PermissionGuardedTool(wrapped, mgr)
    context = _make_context(role="member")

    result = await guarded.call(context)
    assert called
    assert result == "ok"


@pytest.mark.asyncio
async def test_guarded_tool_blocks_when_permission_denied():
    sp.put(
        "tool_permissions",
        {"_default": {"blocked_tool": "admin"}},
        scope="global",
        scope_id="global",
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
        _clear_tool_permissions()


@pytest.mark.asyncio
async def test_guarded_tool_delegates_to_wrapped_call():
    _clear_tool_permissions()
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
async def test_guarded_tool_handles_async_generator_handler():
    _clear_tool_permissions()
    mgr = FunctionToolManager()

    async def gen_handler(ctx, **kw):  # type: ignore[misc]
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


def test_get_full_tool_set_excludes_builtin_tools():
    """Builtin tools are added separately by astr_main_agent.py, not through
    get_full_tool_set()."""
    mgr = FunctionToolManager()
    tool_set = mgr.get_full_tool_set()

    names = {t.name for t in tool_set.tools}
    # Builtin tools are injected individually by the agent builder —
    # they must NOT appear in the generic tool set.
    assert "astrbot_execute_shell" not in names


def test_get_full_tool_set_wraps_non_builtin():
    mgr = FunctionToolManager()
    _clear_tool_permissions()

    mgr.func_list.append(_dummy_tool("my_plugin_tool"))
    tool_set = mgr.get_full_tool_set()

    plugin_tools = [t for t in tool_set.tools if t.name == "my_plugin_tool"]
    assert plugin_tools
    assert isinstance(plugin_tools[0], _PermissionGuardedTool), (
        "non-builtin tools must be wrapped"
    )


# ── API: get_tool_list permission fields ──────────────────────────────


class TestGetToolListPermission:
    @pytest.mark.asyncio
    async def test_list_includes_permission_fields_for_non_builtin(self):
        service = _make_tools_service()
        sp.put(
            "tool_permissions",
            {"_default": {"my_plugin_tool": "admin"}},
            scope="global",
            scope_id="global",
        )
        try:
            service.tool_mgr.func_list.append(_dummy_tool("my_plugin_tool"))
            tools = service.get_tool_list()

            target = next(t for t in tools if t["name"] == "my_plugin_tool")
            assert target["permission"] == "admin"
            assert target["permission_configured"] is True
            assert target["readonly"] is False
        finally:
            _clear_tool_permissions()

    @pytest.mark.asyncio
    async def test_list_no_permission_fields_for_builtin(self):
        service = _make_tools_service()
        tools = service.get_tool_list()

        target = next(t for t in tools if t["name"] == "astrbot_execute_shell")
        assert "permission" not in target
        assert "permission_configured" not in target
        assert target["readonly"] is True


# ── API: update_tool_permission ──────────────────────────────────────


class TestUpdateToolPermission:
    @pytest.mark.asyncio
    async def test_set_admin_permission(self):
        service = _make_tools_service()
        service.tool_mgr.func_list.append(_dummy_tool("target_tool"))
        _clear_tool_permissions()

        message = service.update_tool_permission(
            {"name": "target_tool", "permission": "admin"}
        )
        assert "target_tool" in message

        stored = sp.get("tool_permissions", {}, scope="global", scope_id="global")
        assert stored["_default"]["target_tool"] == "admin"

    @pytest.mark.asyncio
    async def test_reject_builtin_tool(self):
        service = _make_tools_service()

        with pytest.raises(ToolsServiceError, match="Builtin"):
            service.update_tool_permission(
                {"name": "astrbot_execute_shell", "permission": "admin"}
            )

    @pytest.mark.asyncio
    async def test_reject_unknown_tool(self):
        service = _make_tools_service()

        with pytest.raises(ToolsServiceError, match="not found"):
            service.update_tool_permission(
                {"name": "ghost_tool", "permission": "admin"}
            )

    @pytest.mark.asyncio
    async def test_reject_invalid_permission_value(self):
        service = _make_tools_service()
        service.tool_mgr.func_list.append(_dummy_tool("target_tool"))

        with pytest.raises(ToolsServiceError, match="admin or member"):
            service.update_tool_permission(
                {"name": "target_tool", "permission": "everyone"}
            )
