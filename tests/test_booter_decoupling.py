"""TDD tests for booter decoupling refactoring.

Tests written BEFORE implementation — all should initially FAIL (red).
After each implementation step, the corresponding tests should turn green.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ═══════════════════════ Step 1: 常量 ═══════════════════════


class TestBooterConstants:
    def test_constants_exist(self):
        from astrbot.core.computer.booters.constants import (
            BOOTER_BOXLITE,
            BOOTER_SHIPYARD,
            BOOTER_SHIPYARD_NEO,
        )

        assert BOOTER_SHIPYARD == "shipyard"
        assert BOOTER_SHIPYARD_NEO == "shipyard_neo"
        assert BOOTER_BOXLITE == "boxlite"


# ═══════════════════════ Step 2: Prompt 常量 ═══════════════════════


class TestNeoPromptConstants:
    def test_neo_file_path_prompt_exists(self):
        from astrbot.core.computer.prompts import NEO_FILE_PATH_PROMPT

        assert "relative" in NEO_FILE_PATH_PROMPT.lower()
        assert "workspace" in NEO_FILE_PATH_PROMPT.lower()

    def test_neo_skill_lifecycle_prompt_exists(self):
        from astrbot.core.computer.prompts import NEO_SKILL_LIFECYCLE_PROMPT

        assert "astrbot_create_skill_payload" in NEO_SKILL_LIFECYCLE_PROMPT
        assert "astrbot_promote_skill_candidate" in NEO_SKILL_LIFECYCLE_PROMPT


# ═══════════════════════ Step 3: 基类接口 ═══════════════════════


class TestComputerBooterBaseInterface:
    def test_get_default_tools_returns_empty(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        assert ComputerBooter.get_default_tools() == []

    def test_get_system_prompt_parts_returns_empty(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        assert ComputerBooter.get_system_prompt_parts() == []


# ═══════════════════════ Step 4: Booter 子类工具声明 ═══════════════════════


class TestShipyardBooterTools:
    def test_get_default_tools_returns_4(self):
        from astrbot.core.computer.booters.shipyard import ShipyardBooter

        tools = ShipyardBooter.get_default_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "astrbot_execute_shell" in names
        assert "astrbot_execute_ipython" in names
        assert "astrbot_upload_file" in names
        assert "astrbot_download_file" in names

    def test_get_system_prompt_parts_empty(self):
        from astrbot.core.computer.booters.shipyard import ShipyardBooter

        assert ShipyardBooter.get_system_prompt_parts() == []


class TestShipyardNeoBooterTools:
    def _make_booter(self, caps=None):
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        booter = ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
        )
        if caps is not None:
            booter._sandbox = SimpleNamespace(capabilities=caps)
        return booter

    def test_get_default_tools_returns_18(self):
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        tools = ShipyardNeoBooter.get_default_tools()
        assert len(tools) == 18  # 4 base + 11 Neo + 3 browser
        names = {t.name for t in tools}
        assert "astrbot_execute_browser" in names
        assert "astrbot_create_skill_candidate" in names
        assert "astrbot_execute_shell" in names

    def test_get_tools_no_boot_returns_default(self):
        booter = self._make_booter()
        tools = booter.get_tools()
        assert len(tools) == 18

    def test_get_tools_with_browser(self):
        booter = self._make_booter(caps=["python", "shell", "filesystem", "browser"])
        tools = booter.get_tools()
        assert len(tools) == 18
        names = {t.name for t in tools}
        assert "astrbot_execute_browser" in names

    def test_get_tools_without_browser(self):
        booter = self._make_booter(caps=["python", "shell", "filesystem"])
        tools = booter.get_tools()
        assert len(tools) == 15  # no browser
        names = {t.name for t in tools}
        assert "astrbot_execute_browser" not in names
        assert "astrbot_create_skill_candidate" in names

    def test_get_system_prompt_parts_has_neo_prompts(self):
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        parts = ShipyardNeoBooter.get_system_prompt_parts()
        assert len(parts) == 2
        combined = "".join(parts)
        assert "relative" in combined.lower()
        assert "astrbot_create_skill_payload" in combined


class TestBoxliteBooterTools:
    def test_get_default_tools_returns_4(self):
        pytest.importorskip("boxlite")
        from astrbot.core.computer.booters.boxlite import BoxliteBooter

        tools = BoxliteBooter.get_default_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "astrbot_execute_shell" in names

    def test_get_system_prompt_parts_empty(self):
        pytest.importorskip("boxlite")
        from astrbot.core.computer.booters.boxlite import BoxliteBooter

        assert BoxliteBooter.get_system_prompt_parts() == []


# ═══════════════════════ Step 5: computer_client API ═══════════════════════


class TestComputerClientAPI:
    def test_get_sandbox_tools_unknown_session(self):
        from astrbot.core.computer.computer_client import get_sandbox_tools

        with patch("astrbot.core.computer.computer_client.session_booter", {}):
            assert get_sandbox_tools("unknown") == []

    def test_get_sandbox_tools_with_booted_session(self):
        from astrbot.core.computer.computer_client import get_sandbox_tools

        fake_booter = SimpleNamespace(
            get_tools=lambda: ["tool1", "tool2"],
        )
        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {"s1": fake_booter},
        ):
            assert get_sandbox_tools("s1") == ["tool1", "tool2"]

    def test_get_default_sandbox_tools_neo(self):
        from astrbot.core.computer.computer_client import get_default_sandbox_tools

        tools = get_default_sandbox_tools({"booter": "shipyard_neo"})
        assert len(tools) == 18

    def test_get_default_sandbox_tools_shipyard(self):
        from astrbot.core.computer.computer_client import get_default_sandbox_tools

        tools = get_default_sandbox_tools({"booter": "shipyard"})
        assert len(tools) == 4

    def test_get_default_sandbox_tools_boxlite(self):
        pytest.importorskip("boxlite")
        from astrbot.core.computer.computer_client import get_default_sandbox_tools

        tools = get_default_sandbox_tools({"booter": "boxlite"})
        assert len(tools) == 4

    def test_get_default_sandbox_tools_unknown_type(self):
        from astrbot.core.computer.computer_client import get_default_sandbox_tools

        tools = get_default_sandbox_tools({"booter": "nonexistent"})
        assert tools == []

    def test_get_sandbox_prompt_parts_neo(self):
        from astrbot.core.computer.computer_client import get_sandbox_prompt_parts

        parts = get_sandbox_prompt_parts({"booter": "shipyard_neo"})
        assert len(parts) == 2

    def test_get_sandbox_prompt_parts_shipyard(self):
        from astrbot.core.computer.computer_client import get_sandbox_prompt_parts

        parts = get_sandbox_prompt_parts({"booter": "shipyard"})
        assert parts == []


# ═══════════════════════ Step 6+7: 集成测试 ═══════════════════════


class TestApplySandboxToolsRefactored:
    """ComputerToolProvider replaces _apply_sandbox_tools for tool/prompt injection.

    _apply_sandbox_tools has been removed. Tool injection is now handled entirely
    by ComputerToolProvider.get_tools() / get_system_prompt_addon().
    """

    def _tool_names(self, tools: list) -> set[str]:
        return {t.name for t in tools}

    def test_neo_tools_registered_via_provider(self):
        """get_tools() returns full neo tool set (18 tools) for sandbox/neo config."""
        try:
            from astrbot.core.computer.computer_tool_provider import (
                ComputerToolProvider,
            )
            from astrbot.core.tool_provider import ToolProviderContext
        except ImportError:
            pytest.skip("circular import")
        ctx = ToolProviderContext(
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "shipyard_neo"},
        )
        tools = ComputerToolProvider().get_tools(ctx)
        names = self._tool_names(tools)
        assert "astrbot_create_skill_candidate" in names, "neo skill tool missing"
        assert "astrbot_execute_browser" in names, "browser tool missing from full schema"
        assert "astrbot_execute_shell" in names, "shell tool missing"
        assert "astrbot_execute_ipython" in names, "python tool missing"
        assert len(names) == 18, f"expected 18 tools, got {len(names)}: {sorted(names)}"

    def test_neo_prompt_injected_via_provider(self):
        """get_system_prompt_addon() includes sandbox hint and neo-specific fragments."""
        try:
            from astrbot.core.computer.computer_tool_provider import (
                ComputerToolProvider,
            )
            from astrbot.core.tool_provider import ToolProviderContext
        except ImportError:
            pytest.skip("circular import")
        ctx = ToolProviderContext(
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "shipyard_neo"},
        )
        prompt = ComputerToolProvider().get_system_prompt_addon(ctx)
        assert len(prompt) > 0, "prompt addon must not be empty for sandbox/neo"
        assert "sandbox" in prompt.lower(), "sandbox hint must be present"
        # Verify neo-specific content (file path rule + skill lifecycle) is included
        assert "path" in prompt.lower() or "relative" in prompt.lower(), (
            "file path rule fragment missing from neo prompt"
        )

    def test_shipyard_no_neo_prompt_via_provider(self):
        """Shipyard config: get_tools returns 4 tools, prompt has no neo lifecycle text."""
        try:
            from astrbot.core.computer.computer_tool_provider import (
                ComputerToolProvider,
            )
            from astrbot.core.tool_provider import ToolProviderContext
        except ImportError:
            pytest.skip("circular import")
        ctx = ToolProviderContext(
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard",
                "shipyard_endpoint": "http://localhost:8080",
                "shipyard_access_token": "test-token",
            },
        )
        tools = ComputerToolProvider().get_tools(ctx)
        prompt = ComputerToolProvider().get_system_prompt_addon(ctx)
        names = self._tool_names(tools)
        assert len(names) == 4, (
            f"shipyard must have exactly 4 tools, got {len(names)}: {sorted(names)}"
        )
        assert "astrbot_create_skill_candidate" not in names, (
            "neo skill tools must not appear for shipyard"
        )
        assert "astrbot_execute_browser" not in names, (
            "browser tools must not appear for shipyard"
        )
        assert "Neo Skill Lifecycle" not in prompt
        assert "astrbot_create_skill_payload" not in prompt

    def test_full_toolset_always_injected_for_cache_stability(self):
        """Full 18-tool schema always returned regardless of boot state.

        Cache-stability design: browser tools appear in the schema even for
        non-browser sessions so the schema byte-content is stable across the
        entire conversation (enabling LLM provider prefix cache hits).
        The executor rejects browser calls when the capability is absent.
        """
        try:
            from astrbot.core.computer.computer_tool_provider import (
                ComputerToolProvider,
            )
            from astrbot.core.tool_provider import ToolProviderContext
        except ImportError:
            pytest.skip("circular import")
        ctx = ToolProviderContext(
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "shipyard_neo"},
        )
        # ComputerToolProvider always calls get_default_sandbox_tools(), never
        # the post-boot capability-filtered get_tools() — schema must be stable.
        tools = ComputerToolProvider().get_tools(ctx)
        names = self._tool_names(tools)
        assert "astrbot_execute_browser" in names, (
            "browser tool must be in full schema for cache stability"
        )
        assert "astrbot_execute_browser_batch" in names
        assert "astrbot_run_browser_skill" in names
        assert len(names) == 18, (
            f"full neo schema must have 18 tools, got {len(names)}: {sorted(names)}"
        )

    def test_none_runtime_returns_empty(self):
        """runtime='none' must return no tools and no prompt addon."""
        try:
            from astrbot.core.computer.computer_tool_provider import (
                ComputerToolProvider,
            )
            from astrbot.core.tool_provider import ToolProviderContext
        except ImportError:
            pytest.skip("circular import")
        ctx = ToolProviderContext(computer_use_runtime="none", sandbox_cfg={})
        assert ComputerToolProvider().get_tools(ctx) == []
        assert ComputerToolProvider().get_system_prompt_addon(ctx) == ""

    def test_shipyard_missing_endpoint_returns_empty(self):
        """Shipyard config without endpoint/token must return [] (not crash)."""
        try:
            from astrbot.core.computer.computer_tool_provider import (
                ComputerToolProvider,
            )
            from astrbot.core.tool_provider import ToolProviderContext
        except ImportError:
            pytest.skip("circular import")
        ctx = ToolProviderContext(
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "shipyard"},  # no endpoint/token
        )
        tools = ComputerToolProvider().get_tools(ctx)
        assert tools == [], "missing shipyard credentials must return empty tool list"


class TestExecutorCapabilityGuard:
    """_check_sandbox_capability enforces executor-side browser capability rejection."""

    def test_browser_tool_rejected_without_browser_cap(self):
        """Browser tool is rejected when booted session has no browser capability."""
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        from unittest.mock import MagicMock

        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        tool = MagicMock()
        tool.name = "astrbot_execute_browser"
        run_context = MagicMock()
        run_context.context.event.unified_msg_origin = "test-session-no-browser"

        fake_booter = ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
        )
        fake_booter._sandbox = SimpleNamespace(
            capabilities=["python", "shell", "filesystem"]
        )

        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {"test-session-no-browser": fake_booter},
        ):
            result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)

        assert result is not None, "must return rejection for missing browser capability"
        assert result.isError is True
        assert "browser" in str(result.content).lower()
        assert "capability" in str(result.content).lower()

    def test_browser_tool_allowed_with_browser_cap(self):
        """Browser tool is allowed when booted session has browser capability."""
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        from unittest.mock import MagicMock

        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        tool = MagicMock()
        tool.name = "astrbot_execute_browser"
        run_context = MagicMock()
        run_context.context.event.unified_msg_origin = "test-session-browser"

        fake_booter = ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
        )
        fake_booter._sandbox = SimpleNamespace(
            capabilities=["python", "shell", "filesystem", "browser"]
        )

        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {"test-session-browser": fake_booter},
        ):
            result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)

        assert result is None, "must allow browser tool when browser capability is present"

    def test_all_browser_tool_names_are_rejected(self):
        """All 3 browser tool names are blocked when browser cap is absent."""
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        from unittest.mock import MagicMock

        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        fake_booter = ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
        )
        fake_booter._sandbox = SimpleNamespace(capabilities=["python", "shell"])

        browser_tool_names = [
            "astrbot_execute_browser",
            "astrbot_execute_browser_batch",
            "astrbot_run_browser_skill",
        ]
        for name in browser_tool_names:
            tool = MagicMock()
            tool.name = name
            run_context = MagicMock()
            run_context.context.event.unified_msg_origin = "test-session"
            with patch(
                "astrbot.core.computer.computer_client.session_booter",
                {"test-session": fake_booter},
            ):
                result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)
            assert result is not None and result.isError is True, (
                f"browser tool '{name}' must be rejected without browser cap"
            )

    def test_non_browser_tool_always_allowed(self):
        """Non-browser tools bypass capability check entirely."""
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        from unittest.mock import MagicMock

        non_browser_names = [
            "astrbot_execute_shell",
            "astrbot_execute_ipython",
            "astrbot_file_upload",
            "astrbot_create_skill_candidate",
        ]
        for name in non_browser_names:
            tool = MagicMock()
            tool.name = name
            run_context = MagicMock()
            result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)
            assert result is None, f"non-browser tool '{name}' must not be blocked"

    def test_unbooted_session_allows_browser_tool(self):
        """Browser tool is allowed when sandbox is not yet booted (caps=None)."""
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        from unittest.mock import MagicMock

        tool = MagicMock()
        tool.name = "astrbot_execute_browser"
        run_context = MagicMock()
        run_context.context.event.unified_msg_origin = "unbooted-session"

        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {},  # no booter registered ￫ caps=None ￫ allow through
        ):
            result = FunctionToolExecutor._check_sandbox_capability(tool, run_context)

        assert result is None, (
            "must allow browser tool when sandbox not yet booted (boot gate handles it)"
        )


class TestSubagentHandoffTools:
    """Subagent should get same tools as main agent."""

    def test_sandbox_runtime_gets_neo_tools(self):
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        with patch("astrbot.core.computer.computer_client.session_booter", {}):
            tools = FunctionToolExecutor._get_runtime_computer_tools(
                "sandbox",
                session_id=None,
                sandbox_cfg={"booter": "shipyard_neo"},
            )
        assert "astrbot_create_skill_candidate" in tools
        assert len(tools) == 18

    def test_sandbox_runtime_shipyard_only_4(self):
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        with patch("astrbot.core.computer.computer_client.session_booter", {}):
            tools = FunctionToolExecutor._get_runtime_computer_tools(
                "sandbox",
                session_id=None,
                sandbox_cfg={"booter": "shipyard"},
            )
        assert len(tools) == 0

    def test_sandbox_runtime_empty_config_still_gets_default_tools(self):
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        tools = FunctionToolExecutor._get_runtime_computer_tools(
            "sandbox",
            session_id=None,
            sandbox_cfg={},
        )
        assert "astrbot_create_skill_candidate" in tools
        assert len(tools) == 18

    def test_local_runtime_unchanged(self):
        try:
            from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        except ImportError:
            pytest.skip("circular import")
        tools = FunctionToolExecutor._get_runtime_computer_tools(
            "local",
            session_id=None,
            sandbox_cfg={},
        )
        assert len(tools) == 2
