"""Tests for FunctionToolManager with new internal tools architecture."""

import asyncio
import json

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_tool_provider import get_all_tools
from astrbot.core.provider import func_tool_manager as ftm
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.tools.computer_tools.shell import ExecuteShellTool
from astrbot.core.tools.web_search_tools import (
    TavilyExtractWebPageTool,
    TavilyWebSearchTool,
)


def _make_fake_wrapper_class():
    class FakeConfig:
        def get_config(self, umo):
            return {"provider_settings": {"computer_use_runtime": "sandbox"}}

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper(ContextWrapper[AstrAgentContext]):
        def __init__(self):
            self.context = FakeAstrContext()  # type: ignore[assignment]
            self.messages = []

    return FakeWrapper


def test_computer_tools_provider_returns_tools():
    """ComputerToolProvider should return a list of computer tools."""
    tools = get_all_tools()

    assert len(tools) > 0
    names = [t.name for t in tools]
    assert "astrbot_execute_shell" in names


def test_register_internal_tools_adds_tools_to_manager():
    """register_internal_tools should add computer tools to the manager."""
    manager = FunctionToolManager()

    tool = manager.get_func("astrbot_execute_shell")
    assert tool is not None
    assert tool.name == "astrbot_execute_shell"


def test_manager_func_list_starts_empty():
    """func_list should start empty in new architecture."""
    manager = FunctionToolManager()

    assert manager.func_list == []


def test_register_internal_tools_does_not_duplicate():
    """Calling register_internal_tools twice should not duplicate tools."""
    manager = FunctionToolManager()

    first_tool = manager.get_func("astrbot_execute_shell")
    assert first_tool is not None

    # Should still have the same tool (not duplicated)
    second_tool = manager.get_func("astrbot_execute_shell")
    assert second_tool is first_tool
    assert first_tool is not None
    assert first_tool.parameters["properties"]["background"]["default"] is False  # type: ignore[union-attr]
    assert manager.is_builtin_tool("astrbot_execute_shell") is True


@pytest.mark.asyncio
async def test_execute_shell_defaults_to_foreground(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    calls = []

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            calls.append({"command": command, "background": background})
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

    FakeWrapper = _make_fake_wrapper_class()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)

    result = await ExecuteShellTool().call(
        FakeWrapper(), command="chromium https://example.com"
    )

    assert isinstance(result, str)
    assert json.loads(result)["success"] is True
    assert calls == [{"command": "chromium https://example.com", "background": False}]


@pytest.mark.asyncio
async def test_execute_shell_uses_fresh_default_env_per_call(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    calls = []

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            assert env is not None
            env["MUTATED_BY_FAKE_SHELL"] = command
            calls.append(env.copy())
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

    FakeWrapper = _make_fake_wrapper_class()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)
    tool = ExecuteShellTool()

    await tool.call(FakeWrapper(), command="first")
    await tool.call(FakeWrapper(), command="second")

    assert calls[0]["MUTATED_BY_FAKE_SHELL"] == "first"
    assert calls[1] == {"MUTATED_BY_FAKE_SHELL": "second"}


@pytest.mark.asyncio
async def test_execute_shell_copies_user_env_before_execution(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    calls = []

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            assert env is not None
            env["MUTATED_BY_FAKE_SHELL"] = command
            calls.append(env.copy())
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

    FakeWrapper = _make_fake_wrapper_class()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)
    original_env = {"FOO": "bar"}

    await ExecuteShellTool().call(FakeWrapper(), command="first", env=original_env)

    assert original_env == {"FOO": "bar"}
    assert calls == [{"FOO": "bar", "MUTATED_BY_FAKE_SHELL": "first"}]


@pytest.mark.asyncio
async def test_execute_shell_passes_background_flag_directly(monkeypatch):
    """In the new architecture, background flag is passed directly to shell exec."""
    from astrbot.core.tools.computer_tools import shell as shell_tools

    calls = []

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            calls.append({"command": command, "background": background})
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

    FakeWrapper = _make_fake_wrapper_class()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)

    # nohup is self-detached, so effective_background becomes False
    command = "nohup firefox >/tmp/astrbot-firefox.log 2>&1 &"
    result = await ExecuteShellTool().call(
        FakeWrapper(), command=command, background=True
    )

    assert isinstance(result, str)
    assert json.loads(result)["success"] is True
    assert calls == [{"command": command, "background": False}]

    command2 = "firefox & # already detached"
    result2 = await ExecuteShellTool().call(
        FakeWrapper(), command=command2, background=True
    )

    assert isinstance(result2, str)
    assert json.loads(result2)["success"] is True
    assert calls[1] == {"command": command2, "background": False}


@pytest.mark.asyncio
async def test_execute_shell_reports_exception_type(monkeypatch):
    """Error message uses e!s formatting (may omit class name if __str__ is blank)."""
    from astrbot.core.tools.computer_tools import shell as shell_tools

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            raise ValueError("custom error")

    class FakeBooter:
        shell = FakeShell()

    FakeWrapper = _make_fake_wrapper_class()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)

    result = await ExecuteShellTool().call(FakeWrapper(), command="firefox")

    assert result == "Error executing command: custom error"


def test_tavily_tools_are_registered_as_builtin_tools():
    manager = FunctionToolManager()

    search_tool = manager.get_builtin_tool(TavilyWebSearchTool)
    extract_tool = manager.get_builtin_tool(TavilyExtractWebPageTool)

    assert search_tool.name == "web_search_tavily"
    assert extract_tool.name == "tavily_extract_web_page"
    assert manager.is_builtin_tool("web_search_tavily") is True
    assert manager.is_builtin_tool("tavily_extract_web_page") is True


@pytest.mark.asyncio
async def test_mcp_shutdown_cleanup_runs_in_lifecycle_task(monkeypatch):
    """Disabling an MCP server must clean up in the task that connected.

    anyio cancel scopes entered in connect_to_server() can only be exited
    from the same task, otherwise the scope state is corrupted and its
    cancellation loop spins at 100% CPU (#9068).
    """
    manager = FunctionToolManager()
    seen = {}

    async def fake_connect(self, config, name):
        seen["connect_task"] = asyncio.current_task()

    async def fake_list_tools(self):
        self.tools = []

    async def fake_cleanup(self):
        seen["cleanup_task"] = asyncio.current_task()

    monkeypatch.setattr(ftm.MCPClient, "connect_to_server", fake_connect)
    monkeypatch.setattr(ftm.MCPClient, "list_tools_and_save", fake_list_tools)
    monkeypatch.setattr(ftm.MCPClient, "cleanup", fake_cleanup)

    await manager.enable_mcp_server("dummy", {"command": "python"}, timeout=5)
    await manager.disable_mcp_server("dummy", timeout=5)

    assert seen["cleanup_task"] is seen["connect_task"]
    assert "dummy" not in manager.mcp_client_dict


@pytest.mark.asyncio
async def test_mcp_shutdown_cleanup_survives_late_cancellation(monkeypatch):
    """A cancellation arriving mid-cleanup must not abort the cleanup."""
    manager = FunctionToolManager()
    cleanup_calls = []

    async def fake_connect(self, config, name):
        pass

    async def fake_list_tools(self):
        self.tools = []

    async def fake_cleanup(self):
        cleanup_calls.append(asyncio.current_task())
        if len(cleanup_calls) == 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(ftm.MCPClient, "connect_to_server", fake_connect)
    monkeypatch.setattr(ftm.MCPClient, "list_tools_and_save", fake_list_tools)
    monkeypatch.setattr(ftm.MCPClient, "cleanup", fake_cleanup)

    await manager.enable_mcp_server("dummy", {"command": "python"}, timeout=5)
    await manager.disable_mcp_server("dummy", timeout=5)

    assert len(cleanup_calls) == 2
    assert "dummy" not in manager.mcp_client_dict


@pytest.mark.asyncio
async def test_modelscope_sync_enables_only_synced_servers(monkeypatch):
    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {
                "data": {
                    "mcp_server_list": [
                        {
                            "name": "valid",
                            "operational_urls": [{"url": "https://example.com/mcp"}],
                        },
                        {"name": "missing-url", "operational_urls": []},
                        {"name": "empty-url", "operational_urls": [{}]},
                        {"operational_urls": [{"url": "https://example.com/no-name"}]},
                    ]
                }
            }

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, *_args, **_kwargs):
            return FakeResponse()

    saved_configs = []
    enabled_servers = []
    default_config = {"mcpServers": {}}
    manager = FunctionToolManager()

    async def fake_enable_mcp_server(name, config):
        enabled_servers.append((name, config))

    monkeypatch.setattr(ftm.aiohttp, "ClientSession", lambda: FakeSession())
    monkeypatch.setattr(manager, "load_mcp_config", lambda: default_config)
    monkeypatch.setattr(manager, "save_mcp_config", saved_configs.append)
    monkeypatch.setattr(manager, "enable_mcp_server", fake_enable_mcp_server)

    await manager.sync_modelscope_mcp_servers("token")

    assert default_config == {"mcpServers": {}}
    assert saved_configs == [
        {
            "mcpServers": {
                "valid": {
                    "url": "https://example.com/mcp",
                    "transport": "sse",
                    "active": True,
                    "provider": "modelscope",
                }
            }
        }
    ]
    assert enabled_servers == [
        (
            "valid",
            {
                "url": "https://example.com/mcp",
                "transport": "sse",
                "active": True,
                "provider": "modelscope",
            },
        )
    ]
