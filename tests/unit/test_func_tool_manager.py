import asyncio
import json
from dataclasses import dataclass, field

import pytest

from astrbot.api import FunctionTool
from astrbot.core import sp
from astrbot.core.computer.cua_registry import CuaSandboxRegistry
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.tools.computer_tools.shell import ExecuteShellTool
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.tools.web_search_tools import (
    TavilyExtractWebPageTool,
    TavilyWebSearchTool,
)


def test_get_builtin_tool_by_class_returns_cached_instance():
    manager = FunctionToolManager()

    tool_by_class = manager.get_builtin_tool(SendMessageToUserTool)
    tool_by_name = manager.get_builtin_tool("send_message_to_user")

    assert tool_by_class is tool_by_name
    assert manager.get_func("send_message_to_user") is tool_by_class
    assert tool_by_class.name == "send_message_to_user"


def test_builtin_tool_ignores_inactivated_llm_tools():
    manager = FunctionToolManager()
    sp.put(
        "inactivated_llm_tools",
        ["send_message_to_user"],
        scope="global",
        scope_id="global",
    )

    try:
        tool = manager.get_builtin_tool(SendMessageToUserTool)
        assert tool.active is True
    finally:
        sp.put("inactivated_llm_tools", [], scope="global", scope_id="global")


def test_computer_tools_are_registered_as_builtin_tools():
    manager = FunctionToolManager()

    tool = manager.get_builtin_tool(ExecuteShellTool)

    assert tool.name == "astrbot_execute_shell"
    assert tool.parameters["properties"]["background"]["default"] is False
    assert manager.is_builtin_tool("astrbot_execute_shell") is True


def test_clear_builtin_tool_cache_by_module_prefix_removes_matching_instances():
    manager = FunctionToolManager()

    @dataclass
    class ExampleTool(FunctionTool):
        name: str = "astrbot_test_cached_tool"
        description: str = "Cached tool for eviction testing."
        parameters: dict = field(
            default_factory=lambda: {"type": "object", "properties": {}}
        )

    tool = ExampleTool()
    manager.builtin_func_list[ExampleTool] = tool

    removed = manager.clear_builtin_tool_cache_by_module_prefix(__name__)

    assert removed == ["astrbot_test_cached_tool"]
    assert manager.builtin_func_list == {}


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
        sandbox_id = "sb-shell"
        shell = FakeShell()

        async def available(self):
            return True

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
        async def exec(self, command, cwd=None, background=False, env=None, timeout=None):
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
async def test_execute_shell_logs_execution_details(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    log_messages = []

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            return {"success": True, "stdout": "ok", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()
        sandbox_id = "sb-log"

    class FakeConfig:
        def get_config(self, umo):
            return {"provider_settings": {"computer_use_runtime": "sandbox"}}

    class FakeEvent:
        unified_msg_origin = "umo-log"
        role = "admin"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(
        shell_tools.logger,
        "info",
        lambda message, *args, **kwargs: log_messages.append(message % args),
    )

    await ExecuteShellTool().call(FakeWrapper(), command="pwd", timeout=12)

    assert any(
        "Sandbox shell exec start" in message
        and "session_id=umo-log" in message
        and "sandbox_id=sb-log" in message
        and "command='pwd'" in message
        for message in log_messages
    )
    assert any(
        "Sandbox shell exec done" in message
        and "exit_code=0" in message
        and "elapsed_ms=" in message
        for message in log_messages
    )


@pytest.mark.asyncio
async def test_execute_shell_uses_fresh_default_env_per_call(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    calls = []

    class FakeShell:
        async def exec(self, command, cwd=None, background=False, env=None, timeout=None):
            assert env is not None
            env["MUTATED_BY_FAKE_SHELL"] = command
            calls.append(env.copy())
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

        async def available(self):
            return True

    class FakeConfig:
        def get_config(self, umo):
            return {"provider_settings": {"computer_use_runtime": "sandbox"}}

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

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
        async def exec(self, command, cwd=None, background=False, env=None, timeout=None):
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
        async def exec(self, command, cwd=None, background=False, env=None, timeout=None):
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

    assert json.loads(result)["success"] is True
    assert calls == [{"command": command, "background": False}]


@pytest.mark.asyncio
async def test_execute_shell_refreshes_lease_during_long_running_command(monkeypatch):
    from astrbot.core.computer import computer_client
    from astrbot.core.tools.computer_tools import shell as shell_tools

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            await asyncio.sleep(0.05)
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

    registry = CuaSandboxRegistry(storage_path="/tmp/test-shell-lease-registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-shell",
        sandbox_name="shell-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-a",
        owner_session_id="umo",
        controller_user_id="user-a",
        controller_session_id="umo",
        lease_expires_at=time.time() + 60,
        connect_info={"name": "shell-sandbox", "local": True},
    )
    registry.set_current_sandbox_id("umo", "sb-shell")
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-shell"] = FakeBooter()

    class FakeConfig:
        def get_config(self, umo):
            return {
                "provider_settings": {
                    "computer_use_runtime": "sandbox",
                    "sandbox": {"booter": "cua"},
                }
            }

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()
        tool_call_timeout = 120

    monkeypatch.setattr(shell_tools, "LEASE_KEEPALIVE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(shell_tools, "LEASE_KEEPALIVE_BUFFER_SECONDS", 1)

    before = registry.get_sandbox("sb-shell")["lease_expires_at"]
    await ExecuteShellTool().call(FakeWrapper(), command="ps aux", timeout=30)
    after = registry.get_sandbox("sb-shell")["lease_expires_at"]

    assert after is not None
    assert after > before


@pytest.mark.asyncio
async def test_execute_shell_keepalive_does_not_extend_indefinitely_on_failure(
    monkeypatch,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.tools.computer_tools import shell as shell_tools

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            await asyncio.sleep(0.03)
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        sandbox_id = "sb-shell"
        shell = FakeShell()

        async def available(self):
            return True

    registry = CuaSandboxRegistry(storage_path="/tmp/test-shell-deadline-registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-shell",
        sandbox_name="shell-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-a",
        owner_session_id="umo",
        controller_user_id="user-a",
        controller_session_id="umo",
        lease_expires_at=time.time() + 60,
        connect_info={"name": "shell-sandbox", "local": True},
    )
    registry.set_current_sandbox_id("umo", "sb-shell")
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-shell"] = FakeBooter()

    fake_now = {"value": 1000.0}

    def now():
        return fake_now["value"]

    monkeypatch.setattr(shell_tools.time, "time", now)
    monkeypatch.setattr(computer_client.time, "time", now)
    monkeypatch.setattr(shell_tools, "LEASE_KEEPALIVE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(shell_tools, "LEASE_KEEPALIVE_BUFFER_SECONDS", 1)

    class FakeConfig:
        def get_config(self, umo):
            return {
                "provider_settings": {
                    "computer_use_runtime": "sandbox",
                    "sandbox": {"booter": "cua"},
                }
            }

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()
        tool_call_timeout = 10

    async def advance_time(*args, **kwargs):
        fake_now["value"] += 2.0
        await asyncio.sleep(0)
        raise RuntimeError("command failed")

    computer_client.session_booter["sb-shell"].shell.exec = advance_time

    result = await ExecuteShellTool().call(
        FakeWrapper(), command="apt update", timeout=5
    )
    lease_expires_at = registry.get_sandbox("sb-shell")["lease_expires_at"]

    assert result == "Error executing command: command failed"
    assert lease_expires_at <= 1000.0 + 5 + shell_tools.LEASE_KEEPALIVE_BUFFER_SECONDS


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("echo '#'", False),
        ("echo '&'", False),
        ("echo foo#bar &", True),
        ("echo 'unterminated", False),
        ("firefox & # already detached", True),
        ("nohup firefox >/tmp/astrbot-firefox.log 2>&1 &", True),
        ("firefox", False),
    ],
)
def test_is_self_detached_command_handles_quotes_and_comments(command, expected):
    from astrbot.core.tools.computer_tools.shell import _is_self_detached_command

    assert _is_self_detached_command(command) is expected


@pytest.mark.asyncio
async def test_execute_shell_reports_exception_type(monkeypatch):
    """Error message uses e!s formatting (may omit class name if __str__ is blank)."""
    from astrbot.core.tools.computer_tools import shell as shell_tools

    class FakeShell:
        async def exec(self, command, cwd=None, background=False, env=None, timeout=None):
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
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    search_tool = manager.get_builtin_tool(TavilyWebSearchTool)
    extract_tool = manager.get_builtin_tool(TavilyExtractWebPageTool)

    assert search_tool.name == "web_search_tavily"
    assert extract_tool.name == "tavily_extract_web_page"
    assert manager.is_builtin_tool("web_search_tavily") is True
    assert manager.is_builtin_tool("tavily_extract_web_page") is True
