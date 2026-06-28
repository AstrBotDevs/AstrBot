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


def test_default_permission_uses_tool_declared_admin():
    """A tool registered with @llm_tool(permission_type=ADMIN) should
    default to admin when no dashboard override exists."""
    mgr = FunctionToolManager()
    mgr.func_list.append(_dummy_tool("declared_admin_tool"))
    mgr.func_list[-1].declared_permission_type = "admin"
    assert mgr._default_permission("declared_admin_tool") == "admin"


def test_default_permission_uses_tool_declared_member():
    mgr = FunctionToolManager()
    mgr.func_list.append(_dummy_tool("declared_member_tool"))
    mgr.func_list[-1].declared_permission_type = "member"
    assert mgr._default_permission("declared_member_tool") == "member"


def test_default_permission_falls_back_when_undeclared():
    mgr = FunctionToolManager()
    mgr.func_list.append(_dummy_tool("undeclared_tool"))
    assert mgr._default_permission("undeclared_tool") == "member"


def test_default_permission_falls_back_on_unexpected_value():
    """An unrecognized declared_permission_type (e.g. a typo like "admim",
    or any future value outside the current "admin"/"member" whitelist)
    must not be treated as valid -- it should fall back to "member" just
    like an undeclared tool, never accidentally granting admin."""
    mgr = FunctionToolManager()
    tool = _dummy_tool("typo_tool")
    tool.declared_permission_type = "admim"
    mgr.func_list.append(tool)
    assert mgr._default_permission("typo_tool") == "member"


def test_default_permission_does_not_crash_on_foreign_tool_object():
    """Regression test: third-party tools registered via add_llm_tools()
    are only type-hinted as FunctionTool, not enforced at runtime. A tool
    object that doesn't inherit FunctionTool (and so lacks
    declared_permission_type entirely) must not crash permission
    resolution with an AttributeError."""

    class HomemadeTool:
        def __init__(self):
            self.name = "homemade_tool"
            self.description = "d"
            self.parameters = {"type": "object", "properties": {}}
            self.active = True

        async def call(self, context, **kwargs):
            return "ok"

    mgr = FunctionToolManager()
    mgr.func_list.append(HomemadeTool())
    assert mgr._default_permission("homemade_tool") == "member"


def test_default_permission_ignores_unknown_tool_name():
    """Tool name not present in func_list (e.g. MCP/builtin) -> 'member'."""
    mgr = FunctionToolManager()
    assert mgr._default_permission("not_in_func_list") == "member"


# ── @llm_tool(permission_type=...) decorator ─────────────────────────


class TestLLMToolPermissionTypeDecorator:
    """End-to-end tests for the @llm_tool permission_type parameter."""

    def setup_method(self):
        _clear_tool_permissions()

    def teardown_method(self):
        _clear_tool_permissions()

    def test_declares_admin_permission_on_tool(self):
        from astrbot.api.event import filter
        from astrbot.core.provider.register import llm_tools

        @filter.llm_tool(
            name="t8947_admin_tool", permission_type=filter.PermissionType.ADMIN
        )
        async def _admin_tool(event):
            """A dangerous admin-only tool."""
            return "ok"

        try:
            tool = llm_tools.get_func("t8947_admin_tool")
            assert tool is not None
            assert tool.declared_permission_type == "admin"
            assert llm_tools._default_permission("t8947_admin_tool") == "admin"
        finally:
            llm_tools.remove_func("t8947_admin_tool")

    def test_declares_member_permission_on_tool(self):
        from astrbot.api.event import filter
        from astrbot.core.provider.register import llm_tools

        @filter.llm_tool(
            name="t8947_member_tool", permission_type=filter.PermissionType.MEMBER
        )
        async def _member_tool(event):
            """An explicitly unrestricted tool."""
            return "ok"

        try:
            tool = llm_tools.get_func("t8947_member_tool")
            assert tool is not None
            assert tool.declared_permission_type == "member"
            assert llm_tools._default_permission("t8947_member_tool") == "member"
        finally:
            llm_tools.remove_func("t8947_member_tool")

    def test_no_permission_type_keeps_legacy_behavior(self):
        """Omitting permission_type must not change any existing behavior."""
        from astrbot.api.event import filter
        from astrbot.core.provider.register import llm_tools

        @filter.llm_tool(name="t8947_default_tool")
        async def _default_tool(event):
            """A tool with no declared permission."""
            return "ok"

        try:
            tool = llm_tools.get_func("t8947_default_tool")
            assert tool is not None
            assert tool.declared_permission_type is None
            assert llm_tools._default_permission("t8947_default_tool") == "member"
        finally:
            llm_tools.remove_func("t8947_default_tool")

    def test_invalid_permission_type_raises(self):
        from astrbot.api.event import filter

        with pytest.raises(ValueError, match="permission_type"):
            @filter.llm_tool(name="t8947_bad_tool", permission_type="admin")
            async def _bad_tool(event):
                """Bad declaration using a raw string instead of the enum."""
                return "ok"

    def test_permission_type_via_agent_llm_tool_raises(self):
        """Regression test: tools registered via Agent.llm_tool (i.e. through
        RegisteringAgent) never get written to func_list, so they don't go
        through _default_permission or the dashboard's permission override.
        Declaring permission_type there used to be silently dropped --
        the tool would look like it had no permission protection at all,
        even though the plugin author explicitly asked for one. It must
        raise instead of silently ignoring the declaration."""
        from astrbot.api.event import filter
        from astrbot.core.agent.agent import Agent
        from astrbot.core.star.register.star_handler import RegisteringAgent

        agent = Agent(name="t8947_test_agent", instructions="test", tools=[])
        registering_agent = RegisteringAgent(agent)

        with pytest.raises(ValueError, match="Agent"):

            @registering_agent.llm_tool(
                name="t8947_agent_tool", permission_type=filter.PermissionType.ADMIN
            )
            async def _agent_tool(event):
                """A tool that should not be registerable with a permission."""
                return "ok"

    def test_agent_llm_tool_without_permission_type_still_works(self):
        """Omitting permission_type on an Agent-registered tool must
        continue to work exactly as before this feature was added."""
        from astrbot.core.agent.agent import Agent
        from astrbot.core.star.register.star_handler import RegisteringAgent

        agent = Agent(name="t8947_test_agent_ok", instructions="test", tools=[])
        registering_agent = RegisteringAgent(agent)

        @registering_agent.llm_tool(name="t8947_agent_tool_ok")
        async def _agent_tool_ok(event):
            """A normal tool with no permission declaration."""
            return "ok"

        assert len(agent.tools) == 1
        assert agent.tools[0].name == "t8947_agent_tool_ok"
        assert agent.tools[0].declared_permission_type is None

    def test_permission_type_passed_positionally_as_name_raises(self):
        """Regression test: forgetting name= / permission_type= and passing
        a PermissionType member as the sole positional argument used to be
        silently accepted -- Python binds it to `name`, and pydantic's str
        coercion mangled it into a near-meaningless tool name (e.g. "1"),
        with no permission protection at all and no indication anything
        went wrong. This must raise a clear error instead."""
        from astrbot.api.event import filter

        with pytest.raises(ValueError, match="PermissionType"):

            @filter.llm_tool(filter.PermissionType.ADMIN)
            async def _typo_tool(event):
                """A tool registered with a common typo."""
                return "ok"

    def test_permission_type_passed_positionally_as_second_arg_raises(self):
        """Regression test: permission_type is keyword-only. Passing it as
        a second positional argument must raise TypeError rather than
        silently relying on parameter-order coincidence (which would break
        the moment the signature gains another positional parameter)."""
        from astrbot.api.event import filter

        with pytest.raises(TypeError):

            @filter.llm_tool("t8947_positional_tool", filter.PermissionType.ADMIN)
            async def _positional_tool(event):
                """A tool registered with permission_type passed positionally."""
                return "ok"

    def test_declared_admin_is_enforced_without_dashboard_config(self):
        """The whole point of the feature: a plugin author's declared
        ADMIN default protects the tool even if the bot owner never
        opens the WebUI panel to configure it."""
        from astrbot.api.event import filter
        from astrbot.core.provider.register import llm_tools

        @filter.llm_tool(
            name="t8947_enforced_tool", permission_type=filter.PermissionType.ADMIN
        )
        async def _enforced_tool(event):
            """Restart the server."""
            return "ok"

        try:
            member_ctx = _make_context(role="member", sender_id="user_999")
            error = llm_tools._check_tool_permission(
                "t8947_enforced_tool", member_ctx
            )
            assert error is not None
            assert "admin" in error.lower()

            admin_ctx = _make_context(role="admin", sender_id="admin_1")
            error = llm_tools._check_tool_permission(
                "t8947_enforced_tool", admin_ctx
            )
            assert error is None
        finally:
            llm_tools.remove_func("t8947_enforced_tool")

    def test_dashboard_override_takes_precedence_over_declared_default(self):
        """An explicit WebUI-configured permission always wins over the
        plugin-declared default."""
        from astrbot.api.event import filter
        from astrbot.core.provider.register import llm_tools

        @filter.llm_tool(
            name="t8947_overridden_tool", permission_type=filter.PermissionType.ADMIN
        )
        async def _overridden_tool(event):
            """Declared admin, but the dashboard demotes it to member."""
            return "ok"

        try:
            sp.put(
                "tool_permissions",
                {"_default": {"t8947_overridden_tool": "member"}},
                scope="global",
                scope_id="global",
            )
            member_ctx = _make_context(role="member", sender_id="user_42")
            error = llm_tools._check_tool_permission(
                "t8947_overridden_tool", member_ctx
            )
            assert error is None
        finally:
            llm_tools.remove_func("t8947_overridden_tool")

    def test_dashboard_serialization_surfaces_declared_default(self):
        """get_tool_list() should expose the plugin-declared default so the
        WebUI can show it (e.g. as a badge) even before any admin override
        has been configured."""
        from astrbot.api.event import filter
        from astrbot.core.provider.register import llm_tools

        @filter.llm_tool(
            name="t8947_listed_tool", permission_type=filter.PermissionType.ADMIN
        )
        async def _listed_tool(event):
            """Listed in the dashboard with a declared admin default."""
            return "ok"

        try:
            service = _make_tools_service(tool_mgr=llm_tools)
            tools = service.get_tool_list()
            target = next(t for t in tools if t["name"] == "t8947_listed_tool")
            assert target["permission"] == "admin"
            assert target["permission_configured"] is False
            assert target["declared_permission_type"] == "admin"
        finally:
            llm_tools.remove_func("t8947_listed_tool")


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
async def test_guarded_tool_delegates_handler_with_event_when_permission_passes():
    _clear_tool_permissions()
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
async def test_guarded_tool_delegates_to_wrapped_run():
    _clear_tool_permissions()
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
    _clear_tool_permissions()
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
