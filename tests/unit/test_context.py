"""Unit tests for astrbot.core.star.context.

Tests Context methods with mock-based isolation.
"""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata, star_map, star_registry
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_dependencies():
    """Create fully isolated mocks for all Context constructor dependencies."""
    return {
        "event_queue": MagicMock(),
        "config": MagicMock(),
        "db": MagicMock(),
        "provider_manager": MagicMock(),
        "platform_manager": MagicMock(),
        "conversation_manager": MagicMock(),
        "message_history_manager": MagicMock(),
        "persona_manager": MagicMock(),
        "astrbot_config_mgr": MagicMock(),
        "knowledge_base_manager": MagicMock(),
        "cron_manager": MagicMock(),
    }


@pytest.fixture
def context(mock_dependencies):
    """Create a Context with all mocks."""
    return Context(
        mock_dependencies["event_queue"],
        mock_dependencies["config"],
        mock_dependencies["db"],
        mock_dependencies["provider_manager"],
        mock_dependencies["platform_manager"],
        mock_dependencies["conversation_manager"],
        mock_dependencies["message_history_manager"],
        mock_dependencies["persona_manager"],
        mock_dependencies["astrbot_config_mgr"],
        mock_dependencies["knowledge_base_manager"],
        mock_dependencies["cron_manager"],
    )


# ---------------------------------------------------------------------------
# Constructor / Init
# ---------------------------------------------------------------------------


class TestContextInit:
    """Context constructor and attribute initialization."""

    def test_init_sets_attributes(self, context, mock_dependencies):
        """All constructor arguments are stored as instance attributes."""
        assert context._event_queue is mock_dependencies["event_queue"]
        assert context._config is mock_dependencies["config"]
        assert context._db is mock_dependencies["db"]
        assert context.provider_manager is mock_dependencies["provider_manager"]
        assert context.platform_manager is mock_dependencies["platform_manager"]
        assert context.conversation_manager is mock_dependencies["conversation_manager"]
        assert context.message_history_manager is mock_dependencies["message_history_manager"]
        assert context.persona_manager is mock_dependencies["persona_manager"]
        assert context.astrbot_config_mgr is mock_dependencies["astrbot_config_mgr"]
        assert context.kb_manager is mock_dependencies["knowledge_base_manager"]
        assert context.cron_manager is mock_dependencies["cron_manager"]

    def test_init_sets_empty_registrations(self, context):
        """Runtime registration containers start empty."""
        assert context._registered_web_apis == []
        assert context._register_tasks == []
        assert context._star_manager is None


# ---------------------------------------------------------------------------
# get_using_provider
# ---------------------------------------------------------------------------


class TestGetUsingProvider:
    """Context.get_using_provider() behavior."""

    def test_returns_provider_when_found(self, context, mock_dependencies):
        """get_using_provider returns the provider from provider_manager."""
        mock_provider = MagicMock()
        mock_provider.__class__.__name__ = "Provider"
        mock_dependencies["provider_manager"].get_using_provider.return_value = (
            mock_provider
        )
        result = context.get_using_provider("test_umo")
        assert result is mock_provider
        mock_dependencies["provider_manager"].get_using_provider.assert_called_once()

    def test_returns_none_when_not_found(self, context, mock_dependencies):
        """get_using_provider returns None when no provider is available."""
        mock_dependencies["provider_manager"].get_using_provider.return_value = None
        result = context.get_using_provider("test_umo")
        assert result is None

    def test_raises_value_error_on_wrong_type(self, context, mock_dependencies):
        """get_using_provider raises ValueError when provider is wrong type."""
        mock_dependencies["provider_manager"].get_using_provider.return_value = (
            "not_a_provider"
        )
        with pytest.raises(ValueError, match="类型不正确"):
            context.get_using_provider("test_umo")


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


class TestGetConfig:
    """Context.get_config() behavior."""

    def test_returns_default_config_without_umo(self, context, mock_dependencies):
        """get_config() returns _config when umo is None."""
        result = context.get_config()
        assert result is mock_dependencies["config"]

    def test_returns_umo_config_when_umo_provided(self, context, mock_dependencies):
        """get_config(umo) delegates to astrbot_config_mgr."""
        mock_umo_config = MagicMock()
        mock_dependencies["astrbot_config_mgr"].get_conf.return_value = mock_umo_config
        result = context.get_config("test_umo")
        assert result is mock_umo_config
        mock_dependencies["astrbot_config_mgr"].get_conf.assert_called_once_with(
            "test_umo"
        )


# ---------------------------------------------------------------------------
# get_registered_star / get_all_stars
# ---------------------------------------------------------------------------


class TestGetRegisteredStar:
    """Context.get_registered_star() behavior."""

    @patch("astrbot.core.star.context.star_registry", new_callable=list)
    def test_finds_star_by_name(self, mock_registry, context):
        """get_registered_star returns the matching StarMetadata."""
        s1 = MagicMock(spec=StarMetadata, name="plugin_a")
        s1.name = "plugin_a"
        s2 = MagicMock(spec=StarMetadata, name="plugin_b")
        s2.name = "plugin_b"
        mock_registry.extend([s1, s2])
        result = context.get_registered_star("plugin_a")
        assert result is s1

    @patch("astrbot.core.star.context.star_registry", new_callable=list)
    def test_returns_none_when_not_found(self, mock_registry, context):
        """get_registered_star returns None when no plugin matches."""
        mock_registry.clear()
        result = context.get_registered_star("nonexistent")
        assert result is None

    def test_get_all_stars_returns_registry(self, context):
        """get_all_stars returns the module-level star_registry list."""
        assert context.get_all_stars() is star_registry


# ---------------------------------------------------------------------------
# register_commands
# ---------------------------------------------------------------------------


class TestRegisterCommands:
    """Context.register_commands() behavior."""

    def test_registers_command_handler(self, context):
        """register_commands creates a StarHandlerMetadata and appends it."""
        async def fake_handler():
            pass

        fake_handler.__module__ = "data.plugins.test.main"
        fake_handler.__qualname__ = "my_command"
        context.register_commands(
            star_name="test_star",
            command_name="/hello",
            desc="Says hello",
            priority=5,
            awaitable=fake_handler,
        )

        handlers = star_handlers_registry.get_handlers_by_module_name(
            "data.plugins.test.main"
        )
        assert len(handlers) == 1
        md = handlers[0]
        assert md.event_type == EventType.AdapterMessageEvent
        assert md.desc == "Says hello"
        assert md.handler is fake_handler

    def test_registers_regex_command(self, context):
        """register_commands with use_regex=True adds a RegexFilter."""
        async def fake_handler():
            pass

        fake_handler.__module__ = "data.plugins.test.main"
        fake_handler.__qualname__ = "regex_cmd"
        context.register_commands(
            star_name="test_star",
            command_name=r"hello.*",
            desc="Regex command",
            priority=1,
            awaitable=fake_handler,
            use_regex=True,
        )

        handlers = star_handlers_registry.get_handlers_by_module_name(
            "data.plugins.test.main"
        )
        assert len(handlers) == 1
        md = handlers[0]
        # Should have a RegexFilter (not a CommandFilter)
        from astrbot.core.star.filter.regex import RegexFilter

        assert any(isinstance(f, RegexFilter) for f in md.event_filters)

    def test_registers_command_with_ignore_prefix(self, context):
        """register_commands with use_regex=False adds a CommandFilter."""
        async def fake_handler():
            pass

        fake_handler.__module__ = "data.plugins.test.main"
        fake_handler.__qualname__ = "cmd_no_regex"
        context.register_commands(
            star_name="test_star",
            command_name="/test",
            desc="A command",
            priority=1,
            awaitable=fake_handler,
            use_regex=False,
        )

        handlers = star_handlers_registry.get_handlers_by_module_name(
            "data.plugins.test.main"
        )
        assert len(handlers) == 1
        md = handlers[0]
        from astrbot.core.star.filter.command import CommandFilter

        assert any(isinstance(f, CommandFilter) for f in md.event_filters)


# ---------------------------------------------------------------------------
# register_web_api
# ---------------------------------------------------------------------------


class TestRegisterWebApi:
    """Context.register_web_api() behavior."""

    def test_registers_new_api(self, context):
        """register_web_api appends a new web API route."""
        async def handler():
            pass

        context.register_web_api(
            route="/api/test",
            view_handler=handler,
            methods=["GET"],
            desc="Test endpoint",
        )
        assert len(context._registered_web_apis) == 1
        assert context._registered_web_apis[0] == (
            "/api/test",
            handler,
            ["GET"],
            "Test endpoint",
        )

    def test_replaces_existing_route_with_same_methods(self, context):
        """register_web_api replaces a previously registered API with same route and methods."""
        async def old_handler():
            pass

        async def new_handler():
            pass

        context.register_web_api(
            route="/api/test",
            view_handler=old_handler,
            methods=["GET"],
            desc="Old handler",
        )
        context.register_web_api(
            route="/api/test",
            view_handler=new_handler,
            methods=["GET"],
            desc="New handler",
        )
        assert len(context._registered_web_apis) == 1
        assert context._registered_web_apis[0][1] is new_handler
        assert context._registered_web_apis[0][3] == "New handler"

    def test_allows_different_methods_on_same_route(self, context):
        """register_web_api treats different HTTP methods as separate entries."""
        async def handler():
            pass

        context.register_web_api(
            route="/api/test",
            view_handler=handler,
            methods=["GET"],
            desc="GET handler",
        )
        context.register_web_api(
            route="/api/test",
            view_handler=handler,
            methods=["POST"],
            desc="POST handler",
        )
        assert len(context._registered_web_apis) == 2


# ---------------------------------------------------------------------------
# add_llm_tools
# ---------------------------------------------------------------------------


class TestAddLLMTools:
    """Context.add_llm_tools() behavior."""

    def test_adds_tool_with_module_path(self, context, mock_dependencies):
        """add_llm_tools appends tools and sets handler_module_path."""
        tool = MagicMock()
        tool.name = "test_tool"
        tool.__module__ = "astrbot.builtin_stars.my_plugin.main"

        mock_dependencies["provider_manager"].llm_tools.func_list = []
        context.add_llm_tools(tool)

        assert tool.handler_module_path == "astrbot.builtin_stars.my_plugin.main"
        assert tool in mock_dependencies["provider_manager"].llm_tools.func_list

    def test_replaces_existing_tool_with_same_name(self, context, mock_dependencies):
        """add_llm_tools replaces an existing tool with the same name."""
        old_tool = MagicMock()
        old_tool.name = "dup_tool"
        old_tool.__module__ = "old.module"

        new_tool = MagicMock()
        new_tool.name = "dup_tool"
        new_tool.__module__ = "new.module"

        mock_dependencies["provider_manager"].llm_tools.func_list = [old_tool]
        context.add_llm_tools(new_tool)

        assert old_tool not in mock_dependencies["provider_manager"].llm_tools.func_list
        assert new_tool in mock_dependencies["provider_manager"].llm_tools.func_list


# ---------------------------------------------------------------------------
# register_llm_tool (deprecated)
# ---------------------------------------------------------------------------


class TestRegisterLLMTool:
    """Context.register_llm_tool() (deprecated) behavior."""

    def test_registers_handler_and_adds_func(self, context, mock_dependencies):
        """register_llm_tool creates a StarHandlerMetadata and adds to func_list."""
        async def handler():
            pass

        handler.__module__ = "data.plugins.p.main"
        handler.__qualname__ = "my_func"
        mock_dependencies["provider_manager"].llt = MagicMock()
        mock_dependencies["provider_manager"].llm_tools.func_list = []

        context.register_llm_tool(
            name="my_tool",
            func_args=[{"type": "string", "name": "arg1"}],
            desc="My tool",
            func_obj=handler,
        )

        # Check StarHandlerMetadata was added
        handlers = star_handlers_registry.get_handlers_by_module_name(
            "data.plugins.p.main"
        )
        assert len(handlers) == 1
        assert handlers[0].event_type == EventType.OnLLMRequestEvent

    def test_calls_add_func_on_manager(self, context, mock_dependencies):
        """register_llm_tool delegates to llm_tools.add_func."""
        async def handler():
            pass

        handler.__module__ = "mod"
        handler.__qualname__ = "fn"
        mock_dependencies["provider_manager"].llm_tools.func_list = []

        context.register_llm_tool(
            name="my_tool",
            func_args=[{"type": "string", "name": "arg1"}],
            desc="desc",
            func_obj=handler,
        )

        mock_dependencies["provider_manager"].llm_tools.add_func.assert_called_once_with(
            "my_tool",
            [{"type": "string", "name": "arg1"}],
            "desc",
            handler,
        )


# ---------------------------------------------------------------------------
# register_task / reset_runtime_registrations
# ---------------------------------------------------------------------------


class TestRegisterTask:
    """Context.register_task() behavior."""

    def test_appends_task(self, context):
        """register_task appends to _register_tasks."""
        async def task():
            pass

        context.register_task(task, "A background task")
        assert task in context._register_tasks


class TestResetRuntimeRegistrations:
    """Context.reset_runtime_registrations() behavior."""

    def test_clears_web_apis_and_tasks(self, context):
        """reset_runtime_registrations clears both containers."""
        async def handler():
            pass

        async def task():
            pass

        context.register_web_api("/api/test", handler, ["GET"], "desc")
        context.register_task(task, "desc")
        assert len(context._registered_web_apis) == 1
        assert len(context._register_tasks) == 1

        context.reset_runtime_registrations()

        assert context._registered_web_apis == []
        assert context._register_tasks == []


# ---------------------------------------------------------------------------
# get_platform / get_platform_inst (deprecated)
# ---------------------------------------------------------------------------


class TestGetPlatform:
    """Context.get_platform() (deprecated) and get_platform_inst()."""

    def test_get_platform_by_string_name(self, context, mock_dependencies):
        """get_platform finds a platform by its name string."""
        platform = MagicMock()
        platform.meta().name = "telegram"
        mock_dependencies["platform_manager"].platform_insts = [platform]

        result = context.get_platform("telegram")
        assert result is platform

    def test_get_platform_returns_none_when_not_found(self, context, mock_dependencies):
        """get_platform returns None when no platform matches."""
        mock_dependencies["platform_manager"].platform_insts = []
        result = context.get_platform("telegram")
        assert result is None

    def test_get_platform_inst_by_id(self, context, mock_dependencies):
        """get_platform_inst finds a platform by its meta id."""
        platform = MagicMock()
        platform.meta().id = "test_id"
        mock_dependencies["platform_manager"].platform_insts = [platform]

        result = context.get_platform_inst("test_id")
        assert result is platform

    def test_get_platform_inst_returns_none(self, context, mock_dependencies):
        """get_platform_inst returns None when no platform matches."""
        platform = MagicMock()
        platform.meta().id = "other_id"
        mock_dependencies["platform_manager"].platform_insts = [platform]
        result = context.get_platform_inst("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# get_db
# ---------------------------------------------------------------------------


class TestGetDB:
    """Context.get_db() behavior."""

    def test_returns_db(self, context, mock_dependencies):
        """get_db returns the _db instance."""
        assert context.get_db() is mock_dependencies["db"]


# ---------------------------------------------------------------------------
# get_event_queue
# ---------------------------------------------------------------------------


class TestGetEventQueue:
    """Context.get_event_queue() behavior."""

    def test_returns_event_queue(self, context, mock_dependencies):
        """get_event_queue returns the _event_queue."""
        assert context.get_event_queue() is mock_dependencies["event_queue"]
