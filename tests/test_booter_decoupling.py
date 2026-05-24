"""Tests for the extracted sandbox runtime boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from astrbot.api import FunctionTool


class TestComputerBooterBaseInterface:
    def test_get_default_tools_returns_empty(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        assert ComputerBooter.get_default_tools() == []

    def test_get_system_prompt_parts_returns_empty(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        assert ComputerBooter.get_system_prompt_parts() == []


class TestComputerClientProviderQueries:
    def test_get_sandbox_tools_unknown_session(self):
        from astrbot.core.computer import computer_client
        from astrbot.core.computer.computer_client import get_sandbox_tools

        with patch.object(computer_client.sandbox_manager, "session_booter", {}):
            assert get_sandbox_tools("unknown") == []

    def test_get_sandbox_tools_with_booted_session(self):
        from astrbot.core.computer import computer_client
        from astrbot.core.computer.computer_client import get_sandbox_tools

        fake_booter = SimpleNamespace(
            get_tools=lambda: ["tool1", "tool2"],
        )
        with patch.object(
            computer_client.sandbox_manager, "session_booter", {"s1": fake_booter}
        ):
            assert get_sandbox_tools("s1") == ["tool1", "tool2"]

    def test_core_no_longer_declares_provider_default_tools(self):
        from astrbot.core.computer.computer_client import get_default_sandbox_tools

        assert get_default_sandbox_tools({"booter": "shipyard_neo"}) == []
        assert get_default_sandbox_tools({"booter": "shipyard"}) == []
        assert get_default_sandbox_tools({"booter": "cua"}) == []

    def test_core_no_longer_declares_provider_prompt_parts(self):
        from astrbot.core.computer.computer_client import get_sandbox_prompt_parts

        assert get_sandbox_prompt_parts({"booter": "shipyard_neo"}) == []
        assert get_sandbox_prompt_parts({"booter": "shipyard"}) == []
        assert get_sandbox_prompt_parts({"booter": "cua"}) == []


class TestComputerToolProviderBoundary:
    def test_sandbox_runtime_without_provider_registered_returns_no_provider_tools(
        self,
    ):
        from astrbot.core.computer.computer_tool_provider import ComputerToolProvider
        from astrbot.core.tool_provider import ToolProviderContext

        ctx = ToolProviderContext(
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "shipyard_neo"},
        )
        assert ComputerToolProvider().get_tools(ctx) == []

    def test_none_runtime_returns_empty(self):
        from astrbot.core.computer.computer_tool_provider import ComputerToolProvider
        from astrbot.core.tool_provider import ToolProviderContext

        ctx = ToolProviderContext(computer_use_runtime="none", sandbox_cfg={})
        assert ComputerToolProvider().get_tools(ctx) == []
        assert ComputerToolProvider().get_system_prompt_addon(ctx) == ""


class TestExecutorCapabilityGuard:
    def test_browser_tool_allowed_when_capabilities_are_unknown(self):
        from unittest.mock import MagicMock

        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

        tool = MagicMock()
        tool.name = "astrbot_execute_browser"
        run_context = MagicMock()
        run_context.context.event.unified_msg_origin = "unbooted-session"

        from astrbot.core.computer import computer_client

        with patch.object(computer_client.sandbox_manager, "session_booter", {}):
            result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)

        assert result is None

    def test_browser_tool_rejected_without_browser_capability(self):
        from unittest.mock import MagicMock

        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

        tool = MagicMock()
        tool.name = "astrbot_execute_browser"
        run_context = MagicMock()
        run_context.context.event.unified_msg_origin = "test-session-no-browser"
        fake_booter = SimpleNamespace(capabilities=("python", "shell"))

        from astrbot.core.computer import computer_client

        with patch.object(
            computer_client.sandbox_manager,
            "session_booter",
            {"test-session-no-browser": fake_booter},
        ):
            result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)

        assert result is not None
        assert result.isError is True
        assert "browser" in str(result.content).lower()

    def test_non_browser_tool_always_allowed(self):
        from unittest.mock import MagicMock

        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

        tool = MagicMock()
        tool.name = "astrbot_execute_shell"
        run_context = MagicMock()

        assert FunctionToolExecutor._check_sandbox_capability(tool, run_context) is None


class TestProviderSpecificRuntimeTools:
    def test_runtime_tool_lookup_includes_registered_provider_tools(self):
        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        from astrbot.core.tools.computer_tools.shell import ExecuteShellTool

        provider_tool = FunctionTool(
            name="astrbot_provider_custom",
            description="provider tool",
            parameters={"type": "object", "properties": {}},
        )
        provider_tool.sandbox_provider_id = "provider-a"

        tool_mgr = SimpleNamespace(
            func_list=[provider_tool],
            get_builtin_tool=lambda cls: (
                cls() if cls is not ExecuteShellTool else ExecuteShellTool()
            ),
        )

        FunctionToolExecutor.clear_runtime_computer_tools_cache()
        tools = FunctionToolExecutor._get_runtime_computer_tools(
            "sandbox",
            tool_mgr,
            "provider-a",
        )

        assert "astrbot_provider_custom" in tools
