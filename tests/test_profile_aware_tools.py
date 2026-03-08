"""Tests for profile-aware sandbox selection and conditional tool registration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ═══════════════════════════════════════════════════════════════
# ShipyardNeoBooter.capabilities
# ═══════════════════════════════════════════════════════════════


class TestShipyardNeoBooterCapabilities:
    """Test capabilities property on ShipyardNeoBooter."""

    def _make_booter(self, sandbox_caps: list[str] | None = None):
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        booter = ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
        )
        if sandbox_caps is not None:
            booter._sandbox = SimpleNamespace(capabilities=sandbox_caps)
        return booter

    def test_none_before_boot(self):
        booter = self._make_booter()
        assert booter.capabilities is None

    def test_returns_tuple_after_boot(self):
        booter = self._make_booter(["python", "shell", "filesystem"])
        assert booter.capabilities == ("python", "shell", "filesystem")
        assert isinstance(booter.capabilities, tuple)

    def test_includes_browser_when_present(self):
        booter = self._make_booter(["python", "shell", "filesystem", "browser"])
        assert "browser" in booter.capabilities

    def test_no_browser_when_absent(self):
        booter = self._make_booter(["python", "shell", "filesystem"])
        assert "browser" not in booter.capabilities

    def test_returns_immutable(self):
        """Verify capabilities returns an immutable tuple."""
        booter = self._make_booter(["python"])
        caps = booter.capabilities
        assert isinstance(caps, tuple)
        with pytest.raises(AttributeError):
            caps.append("mutated")  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════
# _apply_sandbox_tools — conditional browser tool registration
# ═══════════════════════════════════════════════════════════════


def _make_config(booter_type: str = "shipyard_neo"):
    return SimpleNamespace(
        sandbox_cfg={"booter": booter_type},
    )


def _make_req():
    return SimpleNamespace(func_tool=None, system_prompt="")


def _import_apply_sandbox_tools():
    """Import _apply_sandbox_tools, skipping if circular-import fails."""
    try:
        from astrbot.core.astr_main_agent import _apply_sandbox_tools

        return _apply_sandbox_tools
    except ImportError:
        pytest.skip("Cannot import _apply_sandbox_tools (circular import in test env)")


class TestApplySandboxToolsConditional:
    """Verify browser tools are conditionally registered."""

    def _tool_names(self, req) -> set[str]:
        """Extract tool names from a request's func_tool."""
        if req.func_tool is None:
            return set()
        return {t.name for t in req.func_tool.tools}

    def test_no_session_registers_all(self):
        """First request (no booted session) → all tools including browser."""
        fn = _import_apply_sandbox_tools()
        config = _make_config("shipyard_neo")
        req = _make_req()

        with patch(
            "astrbot.core.computer.computer_client.session_booter", {}
        ):
            fn(config, req, "session-1")

        names = self._tool_names(req)
        assert "astrbot_execute_browser" in names
        assert "astrbot_execute_browser_batch" in names
        assert "astrbot_run_browser_skill" in names

    def test_with_browser_capability(self):
        """Booted session with browser capability → browser tools registered."""
        fn = _import_apply_sandbox_tools()
        config = _make_config("shipyard_neo")
        req = _make_req()
        fake_booter = SimpleNamespace(
            capabilities=["python", "shell", "filesystem", "browser"]
        )

        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {"session-1": fake_booter},
        ):
            fn(config, req, "session-1")

        names = self._tool_names(req)
        assert "astrbot_execute_browser" in names

    def test_without_browser_capability(self):
        """Booted session WITHOUT browser capability → browser tools NOT registered."""
        fn = _import_apply_sandbox_tools()
        config = _make_config("shipyard_neo")
        req = _make_req()
        fake_booter = SimpleNamespace(
            capabilities=["python", "shell", "filesystem"]
        )

        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {"session-1": fake_booter},
        ):
            fn(config, req, "session-1")

        names = self._tool_names(req)
        assert "astrbot_execute_browser" not in names
        assert "astrbot_execute_browser_batch" not in names
        assert "astrbot_run_browser_skill" not in names
        # Skill tools should still be registered
        assert "astrbot_get_execution_history" in names

    def test_skill_tools_always_registered(self):
        """Skill lifecycle tools are registered regardless of capabilities."""
        fn = _import_apply_sandbox_tools()
        config = _make_config("shipyard_neo")
        req = _make_req()
        fake_booter = SimpleNamespace(capabilities=["python"])

        with patch(
            "astrbot.core.computer.computer_client.session_booter",
            {"session-1": fake_booter},
        ):
            fn(config, req, "session-1")

        names = self._tool_names(req)
        assert "astrbot_create_skill_candidate" in names
        assert "astrbot_promote_skill_candidate" in names


# ═══════════════════════════════════════════════════════════════
# _resolve_profile
# ═══════════════════════════════════════════════════════════════


class TestResolveProfile:
    """Test smart profile selection logic."""

    def _make_booter(self, profile: str = "python-default"):
        from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter

        return ShipyardNeoBooter(
            endpoint_url="http://localhost:8114",
            access_token="sk-bay-test",
            profile=profile,
        )

    @pytest.mark.asyncio
    async def test_user_specified_profile_honoured(self):
        """User explicitly sets a non-default profile → use it directly."""
        booter = self._make_booter(profile="browser-python")
        client = SimpleNamespace()  # list_profiles should NOT be called
        result = await booter._resolve_profile(client)
        assert result == "browser-python"

    @pytest.mark.asyncio
    async def test_selects_browser_profile(self):
        """When multiple profiles available, prefer one with browser."""

        async def _mock_list_profiles():
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        id="python-default",
                        capabilities=["python", "shell", "filesystem"],
                    ),
                    SimpleNamespace(
                        id="browser-python",
                        capabilities=["python", "shell", "filesystem", "browser"],
                    ),
                ]
            )

        booter = self._make_booter()
        client = SimpleNamespace(list_profiles=_mock_list_profiles)
        result = await booter._resolve_profile(client)
        assert result == "browser-python"

    @pytest.mark.asyncio
    async def test_falls_back_to_default_on_api_error(self):
        """API error → graceful fallback to python-default."""

        async def _failing_list_profiles():
            raise ConnectionError("Bay unreachable")

        booter = self._make_booter()
        client = SimpleNamespace(list_profiles=_failing_list_profiles)
        result = await booter._resolve_profile(client)
        assert result == "python-default"

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_profiles(self):
        """Empty profile list → python-default."""

        async def _empty_list_profiles():
            return SimpleNamespace(items=[])

        booter = self._make_booter()
        client = SimpleNamespace(list_profiles=_empty_list_profiles)
        result = await booter._resolve_profile(client)
        assert result == "python-default"

    @pytest.mark.asyncio
    async def test_single_profile_selected(self):
        """Only one profile available → use it."""

        async def _single_profile():
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        id="python-data",
                        capabilities=["python", "shell", "filesystem"],
                    ),
                ]
            )

        booter = self._make_booter()
        client = SimpleNamespace(list_profiles=_single_profile)
        result = await booter._resolve_profile(client)
        assert result == "python-data"

    @pytest.mark.asyncio
    async def test_auth_error_not_silenced(self):
        """UnauthorizedError must propagate, not be downgraded to fallback."""
        from shipyard_neo.errors import UnauthorizedError

        async def _unauthorized_list_profiles():
            raise UnauthorizedError("bad token")

        booter = self._make_booter()
        client = SimpleNamespace(list_profiles=_unauthorized_list_profiles)
        with pytest.raises(UnauthorizedError):
            await booter._resolve_profile(client)


# ═══════════════════════════════════════════════════════════════
# ComputerBooter base class
# ═══════════════════════════════════════════════════════════════


class TestBaseComputerBooter:
    """Verify base class defaults."""

    def test_capabilities_default_none(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        booter = ComputerBooter()
        assert booter.capabilities is None

    def test_browser_default_none(self):
        from astrbot.core.computer.booters.base import ComputerBooter

        booter = ComputerBooter()
        assert booter.browser is None
