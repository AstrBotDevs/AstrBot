"""Tests for per-tool permission management."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.agent.tool import FunctionTool, get_tool_id
from astrbot.core.tools.function_tool_manager import (
    FunctionToolManager,
    _PermissionGuardedTool,
)
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError


class _MemoryPreferences:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def global_get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    async def global_put(self, key: str, value: object) -> None:
        self.values[key] = value


preferences = _MemoryPreferences()


def _manager() -> FunctionToolManager:
    manager = FunctionToolManager()
    manager.bind_preferences(preferences)
    return manager


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
    asyncio.run(preferences.global_put("tool_permissions", {}))


async def _clear_tool_permissions_async() -> None:
    await preferences.global_put("tool_permissions", {})


def _make_tools_service(
    tool_mgr: FunctionToolManager | None = None,
) -> ToolsService:
    """Create a minimal tools service for permission unit tests."""
    service = ToolsService.__new__(ToolsService)
    service.config_manager = MagicMock()
    service.config_manager.get_conf_list.return_value = []
    service.config_manager.confs = {}
    service.plugin_catalog = MagicMock()
    service.plugin_catalog.get_by_module.return_value = None
    service.preferences = preferences
    service.tool_mgr = tool_mgr or _manager()
    return service


def test_default_permission_is_admin():
    mgr = _manager()
    assert mgr._default_permission("any_mcp_tool") == "admin"


@pytest.mark.asyncio
async def test_check_permission_denies_member_when_no_config():
    await _clear_tool_permissions_async()
    mgr = _manager()
    context = _make_context(role="member")

    error = await mgr._check_tool_permission("no_such_tool", context)
    assert error is not None
    assert "Permission denied" in error


@pytest.mark.asyncio
async def test_check_permission_passes_for_admin_with_admin_tool():
    await preferences.global_put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
    )
    try:
        mgr = _manager()
        context = _make_context(role="admin", sender_id="admin_001")
        error = await mgr._check_tool_permission("dangerous_tool", context)
        assert error is None
    finally:
        await _clear_tool_permissions_async()


@pytest.mark.asyncio
async def test_check_permission_denies_member_for_admin_tool():
    await preferences.global_put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
    )
    try:
        mgr = _manager()
        context = _make_context(role="member", sender_id="user_999")
        error = await mgr._check_tool_permission("dangerous_tool", context)
        assert error is not None
        assert "dangerous_tool" in str(error)
        assert "admin" in str(error).lower()
        assert "user_999" in str(error)
    finally:
        await _clear_tool_permissions_async()


@pytest.mark.asyncio
async def test_check_permission_denies_when_no_event():
    await preferences.global_put(
        "tool_permissions",
        {"_default": {"dangerous_tool": "admin"}},
    )
    try:
        mgr = _manager()

        class FakeWrapper:
            pass

        error = await mgr._check_tool_permission("dangerous_tool", FakeWrapper())
        assert error is not None
        assert "admin" in str(error).lower()
    finally:
        await _clear_tool_permissions_async()


@pytest.mark.asyncio
async def test_check_permission_passes_for_member_when_configured_member():
    await preferences.global_put(
        "tool_permissions",
        {"_default": {"safe_tool": "member"}},
    )
    try:
        mgr = _manager()
        context = _make_context(role="member")
        error = await mgr._check_tool_permission("safe_tool", context)
        assert error is None
    finally:
        await _clear_tool_permissions_async()


@pytest.mark.asyncio
async def test_guarded_tool_delegates_handler_with_event_when_permission_passes():
    await preferences.global_put(
        "tool_permissions", {"_default": {"delegated": "member"}}
    )
    mgr = _manager()

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
    await preferences.global_put(
        "tool_permissions",
        {"_default": {"blocked_tool": "admin"}},
    )
    try:
        mgr = _manager()
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
        await _clear_tool_permissions_async()


@pytest.mark.asyncio
async def test_guarded_tool_delegates_to_wrapped_call():
    await preferences.global_put(
        "tool_permissions", {"_default": {"has_call": "member"}}
    )
    mgr = _manager()

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
async def test_guarded_tool_rejects_legacy_run_only_tools():
    await preferences.global_put(
        "tool_permissions", {"_default": {"has_run": "member"}}
    )
    mgr = _manager()

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
    assert result == "error: tool has no callable handler"


@pytest.mark.asyncio
async def test_guarded_tool_handles_async_generator_handler():
    await preferences.global_put(
        "tool_permissions", {"_default": {"gen_tool": "member"}}
    )
    mgr = _manager()

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
    assert result == "C"


@pytest.mark.asyncio
async def test_guarded_tool_streaming_iterator_preserves_all_yields():
    await preferences.global_put(
        "tool_permissions", {"_default": {"gen_tool_stream": "member"}}
    )
    mgr = _manager()

    async def gen_handler(_event, **_kw):  # type: ignore[misc]
        yield "A"
        yield "B"
        yield "C"

    wrapped = FunctionTool(
        name="gen_tool_stream",
        description="desc",
        parameters={},
        handler=gen_handler,
    )
    guarded = _PermissionGuardedTool(wrapped, mgr)
    context = _make_context()

    assert [item async for item in guarded.iter_call(context)] == ["A", "B", "C"]


def test_get_full_tool_set_excludes_builtin_tools():
    """Builtin tools are added separately by astr_main_agent.py, not here."""
    mgr = _manager()
    tool_set = mgr.get_full_tool_set()

    names = {t.name for t in tool_set.tools}
    assert "astrbot_execute_shell" not in names


def test_get_full_tool_set_wraps_non_builtin():
    mgr = _manager()
    _clear_tool_permissions()

    mgr.func_list.append(_dummy_tool("my_plugin_tool"))
    tool_set = mgr.get_full_tool_set()

    plugin_tools = [t for t in tool_set.tools if t.name == "my_plugin_tool"]
    assert plugin_tools
    assert isinstance(plugin_tools[0], _PermissionGuardedTool)


class TestGetToolListPermission:
    @pytest.mark.asyncio
    async def test_list_includes_permission_fields_for_non_builtin(self):
        service = _make_tools_service()
        await preferences.global_put(
            "tool_permissions",
            {"_default": {"my_plugin_tool": "admin"}},
        )
        try:
            service.tool_mgr.func_list.append(_dummy_tool("my_plugin_tool"))
            tools = await service.get_tool_list()

            target = next(t for t in tools if t["name"] == "my_plugin_tool")
            assert target["permission"] == "admin"
            assert target["permission_configured"] is True
            assert target["readonly"] is False
        finally:
            await _clear_tool_permissions_async()

    @pytest.mark.asyncio
    async def test_list_defaults_non_builtin_permission_to_admin(self):
        service = _make_tools_service()
        service.tool_mgr.func_list.append(_dummy_tool("my_plugin_tool"))

        tools = await service.get_tool_list()

        target = next(t for t in tools if t["name"] == "my_plugin_tool")
        assert target["permission"] == "admin"
        assert target["permission_configured"] is False

    @pytest.mark.asyncio
    async def test_list_no_permission_fields_for_builtin(self):
        service = _make_tools_service()
        tools = await service.get_tool_list()

        target = next(t for t in tools if t["name"] == "astrbot_execute_shell")
        assert "permission" not in target
        assert "permission_configured" not in target
        assert target["readonly"] is True


class TestUpdateToolPermission:
    @pytest.mark.asyncio
    async def test_set_admin_permission(self):
        service = _make_tools_service()
        service.tool_mgr.func_list.append(_dummy_tool("target_tool"))
        await _clear_tool_permissions_async()

        message = await service.update_tool_permission(
            {"name": "target_tool", "permission": "admin"}
        )
        assert "target_tool" in message

        stored = await preferences.global_get("tool_permissions", {})
        assert stored["_default"]["target_tool"] == "admin"

    @pytest.mark.asyncio
    async def test_reject_builtin_tool(self):
        service = _make_tools_service()

        with pytest.raises(ToolsServiceError, match="Builtin"):
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


class TestToolParallelPolicy:
    @pytest.mark.asyncio
    async def test_list_exposes_parallel_identity_and_defaults(self):
        service = _make_tools_service()
        tool = _dummy_tool("parallel_candidate")
        tool.handler_module_path = "data.plugins.example.main"
        service.tool_mgr.func_list.append(tool)

        tools = await service.get_tool_list()
        target = next(item for item in tools if item["name"] == tool.name)

        assert target["tool_id"] == get_tool_id(tool)
        assert target["parallel_policy"] == "unknown"
        assert target["parallel_eligible"] is True
        assert target["parallel_enabled"] is False
        assert target["parallel_execution_enabled"] is False

    @pytest.mark.asyncio
    async def test_toggle_parallel_persists_stable_tool_id(self):
        service = _make_tools_service()
        tool = _dummy_tool("parallel_candidate")
        tool.handler_module_path = "data.plugins.example.main"
        service.tool_mgr.func_list.append(tool)

        await service.toggle_tool_parallel(
            {"tool_id": get_tool_id(tool), "enabled": True}
        )
        stored = await preferences.global_get("tool_parallel_execution", {})
        assert stored["allowed_tool_ids"] == [get_tool_id(tool)]

        await service.set_parallel_enabled(True)
        stored = await preferences.global_get("tool_parallel_execution", {})
        assert stored["enabled"] is True

    @pytest.mark.asyncio
    async def test_parallel_rejects_direct_send_tool(self):
        service = _make_tools_service()
        tool = _dummy_tool("send_message_to_user")
        service.tool_mgr.func_list.append(tool)

        with pytest.raises(ToolsServiceError, match="Direct-send"):
            await service.toggle_tool_parallel(
                {"tool_id": get_tool_id(tool), "enabled": True}
            )

    def test_plugin_owner_uses_strict_module_prefix(self):
        service = _make_tools_service()
        metadata = SimpleNamespace(
            name="Example",
            module_path="data.plugins.example.main",
            root_dir_name=None,
            reserved=False,
        )
        service.plugin_catalog.get_by_module.return_value = None
        service.plugin_catalog.all.return_value = (metadata,)

        child_tool = _dummy_tool("child")
        child_tool.handler_module_path = "data.plugins.example.main.tools"
        sibling_tool = _dummy_tool("sibling")
        sibling_tool.handler_module_path = "data.plugins.exampleland"

        assert service._resolve_plugin_owner(child_tool) is metadata
        assert service._resolve_plugin_owner(sibling_tool) is None
