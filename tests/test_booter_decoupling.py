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

    def test_get_tools_delegates_to_class(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        booter = ComputerBooter()
        assert booter.get_tools() == []

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
    """After refactoring, _apply_sandbox_tools uses unified API."""

    def _tool_names(self, req) -> set[str]:
        if req.func_tool is None:
            return set()
        return {t.name for t in req.func_tool.tools}

    def _neo_default_tools(self):
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        return ShipyardNeoBooter.get_default_tools()

    def _shipyard_default_tools(self):
        from astrbot.core.computer.booters.shipyard import ShipyardBooter

        return ShipyardBooter.get_default_tools()

    def test_neo_tools_registered_via_unified_api(self):
        try:
            from astrbot.core.astr_main_agent import _apply_sandbox_tools
        except ImportError:
            pytest.skip("circular import")
        config = SimpleNamespace(sandbox_cfg={"booter": "shipyard_neo"})
        req = SimpleNamespace(func_tool=None, system_prompt="")
        with (
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_tools",
                return_value=[],
            ),
            patch(
                "astrbot.core.computer.computer_client.get_default_sandbox_tools",
                return_value=self._neo_default_tools(),
            ),
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_prompt_parts",
                return_value=[],
            ),
        ):
            _apply_sandbox_tools(config, req, "session-1")
        names = self._tool_names(req)
        assert "astrbot_create_skill_candidate" in names
        assert "astrbot_execute_browser" in names
        assert len(names) == 18

    def test_neo_prompt_injected(self):
        try:
            from astrbot.core.astr_main_agent import _apply_sandbox_tools
        except ImportError:
            pytest.skip("circular import")
        config = SimpleNamespace(sandbox_cfg={"booter": "shipyard_neo"})
        req = SimpleNamespace(func_tool=None, system_prompt="")
        with (
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_tools",
                return_value=[],
            ),
            patch(
                "astrbot.core.computer.computer_client.get_default_sandbox_tools",
                return_value=[],
            ),
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_prompt_parts",
                return_value=[
                    "\n[Shipyard Neo File Path Rule]\nrelative workspace path\n",
                    "\n[Neo Skill Lifecycle Workflow]\nastrbot_create_skill_payload\n",
                ],
            ),
        ):
            _apply_sandbox_tools(config, req, "session-1")
        assert "relative" in req.system_prompt.lower()
        assert "astrbot_create_skill_payload" in req.system_prompt

    def test_shipyard_no_neo_prompt(self):
        try:
            from astrbot.core.astr_main_agent import _apply_sandbox_tools
        except ImportError:
            pytest.skip("circular import")
        config = SimpleNamespace(sandbox_cfg={"booter": "shipyard"})
        req = SimpleNamespace(func_tool=None, system_prompt="")
        with (
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_tools",
                return_value=[],
            ),
            patch(
                "astrbot.core.computer.computer_client.get_default_sandbox_tools",
                return_value=self._shipyard_default_tools(),
            ),
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_prompt_parts",
                return_value=[],
            ),
        ):
            _apply_sandbox_tools(config, req, "session-1")
        names = self._tool_names(req)
        assert len(names) == 4
        assert "Neo Skill Lifecycle" not in req.system_prompt

    def test_booted_session_without_browser(self):
        """Booted session without browser capability → no browser tools."""
        try:
            from astrbot.core.astr_main_agent import _apply_sandbox_tools
        except ImportError:
            pytest.skip("circular import")
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        fake_booter = ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
        )
        fake_booter._sandbox = SimpleNamespace(
            capabilities=["python", "shell", "filesystem"]
        )
        config = SimpleNamespace(sandbox_cfg={"booter": "shipyard_neo"})
        req = SimpleNamespace(func_tool=None, system_prompt="")
        with (
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_tools",
                return_value=fake_booter.get_tools(),
            ),
            patch(
                "astrbot.core.computer.computer_client.get_default_sandbox_tools",
                return_value=[],
            ),
            patch(
                "astrbot.core.computer.computer_client.get_sandbox_prompt_parts",
                return_value=[],
            ),
        ):
            _apply_sandbox_tools(config, req, "session-1")
        names = self._tool_names(req)
        assert "astrbot_execute_browser" not in names
        assert "astrbot_create_skill_candidate" in names
        assert len(names) == 15


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
        assert len(tools) == 4
        assert "astrbot_create_skill_candidate" not in tools

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
