import asyncio
import inspect
import json
from unittest.mock import AsyncMock

import pytest

from astrbot.core import sp
from astrbot.core.computer.booters.local import LocalShellComponent
from astrbot.core.provider import func_tool_manager as ftm
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.tools.computer_tools.shell import (
    ExecuteShellTool,
    LocalExecuteShellTool,
    ShellSessionTool,
)
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.tools.web_search_tools import (
    FirecrawlExtractWebPageTool,
    FirecrawlWebSearchTool,
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
    assert manager.is_builtin_tool("astrbot_shell_session") is True


def test_local_execute_shell_schema_replaces_background_with_yield():
    tool = LocalExecuteShellTool()

    assert tool.name == "astrbot_execute_shell"
    assert "background" not in tool.parameters["properties"]
    assert tool.parameters["properties"]["yield_time_ms"]["default"] == 10_000
    assert "background" not in inspect.signature(tool.call).parameters


def test_shell_session_schema_supports_line_writes():
    tool = ShellSessionTool()

    assert "write_line" in tool.parameters["properties"]["action"]["enum"]
    assert (
        "LF is appended automatically"
        in tool.parameters["properties"]["chars"]["description"]
    )


@pytest.mark.asyncio
async def test_local_execute_shell_manages_running_and_closed_results(
    monkeypatch,
    tmp_path,
):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    shell = LocalShellComponent()
    shell.exec_managed = AsyncMock(
        return_value={
            "session_id": "sh_test",
            "status": "running",
            "stdout": "ready\n",
            "stderr": "",
            "exit_code": None,
        }
    )

    class FakeBooter:
        pass

    booter = FakeBooter()
    booter.shell = shell

    class FakeConfig:
        def get_config(self, umo):
            return {"provider_settings": {"computer_use_runtime": "local"}}

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        @staticmethod
        def get_sender_id():
            return "admin-user"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

    async def fake_get_booter(context, session_id):
        return booter

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(
        shell_tools,
        "workspace_root_for_context",
        AsyncMock(return_value=tmp_path),
    )
    monotonic_values = iter((10.0, 10.5, 20.0, 21.234, 30.0, 32.346))
    monkeypatch.setattr(shell_tools, "monotonic", lambda: next(monotonic_values))

    result = await LocalExecuteShellTool().call(
        FakeWrapper(),
        command="python server.py",
        yield_time_ms=250,
    )

    assert json.loads(result)["session_id"] == "sh_test"
    shell.exec_managed.assert_awaited_once_with(
        "python server.py",
        owner_id="umo",
        creator_id="admin-user",
        creator_is_admin=True,
        sandboxed=False,
        cwd=str(tmp_path),
        env={},
        timeout=None,
        yield_time_ms=250,
    )
    for status, exit_code, wall_time in (
        ("completed", 0, "1.23"),
        ("failed", 1, "2.35"),
    ):
        shell.exec_managed.return_value = {
            "session_id": "sh_test",
            "pid": 12345,
            "status": status,
            "stdout": "done\n",
            "stderr": "",
            "exit_code": exit_code,
            "cursor": 5,
            "has_more": False,
            "session_closed": True,
        }

        result = await LocalExecuteShellTool().call(
            FakeWrapper(),
            command="echo done",
        )

        assert result == (
            f"Command completed with exit code {exit_code} "
            f"(wall time: {wall_time}s).\nOutput:\ndone\n"
        )


@pytest.mark.asyncio
async def test_local_shell_tools_fail_closed_without_sender_identity(
    monkeypatch,
    tmp_path,
):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    shell = LocalShellComponent()
    shell.exec_managed = AsyncMock()
    shell.list_sessions = AsyncMock()

    class FakeBooter:
        pass

    booter = FakeBooter()
    booter.shell = shell

    class FakeConfig:
        def get_config(self, umo):
            return {"provider_settings": {"computer_use_runtime": "local"}}

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        @staticmethod
        def get_sender_id():
            return ""

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

    async def fake_get_booter(context, session_id):
        return booter

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(
        shell_tools,
        "workspace_root_for_context",
        AsyncMock(return_value=tmp_path),
    )

    execute_result = await LocalExecuteShellTool().call(
        FakeWrapper(),
        command="python server.py",
    )
    session_result = await ShellSessionTool().call(FakeWrapper(), action="list")

    assert execute_result == "Error executing command: sender identity is unavailable."
    assert (
        session_result
        == "Error managing shell session: sender identity is unavailable."
    )
    shell.exec_managed.assert_not_awaited()
    shell.list_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_shell_session_tool_lists_sessions_for_current_owner(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    shell = LocalShellComponent()
    shell.list_sessions = AsyncMock(
        return_value={"sessions": [{"session_id": "sh_test", "status": "running"}]}
    )

    class FakeBooter:
        pass

    booter = FakeBooter()
    booter.shell = shell

    class FakeConfig:
        def get_config(self, umo):
            return {"provider_settings": {"computer_use_runtime": "local"}}

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        @staticmethod
        def get_sender_id():
            return "admin-user"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

    async def fake_get_booter(context, session_id):
        return booter

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)

    result = await ShellSessionTool().call(FakeWrapper(), action="list")

    assert json.loads(result)["sessions"][0]["session_id"] == "sh_test"
    shell.list_sessions.assert_awaited_once_with(
        owner_id="umo",
        requester_id="admin-user",
        requester_is_admin=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "component_action"),
    [
        ("poll", "poll"),
        ("write", "write"),
        ("write_line", "write"),
        ("interrupt", "interrupt"),
        ("terminate", "terminate"),
    ],
)
async def test_shell_session_tool_passes_member_identity_to_session_actions(
    monkeypatch,
    action,
    component_action,
):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    shell = LocalShellComponent()
    operation = AsyncMock(return_value={"session_id": "sh_test", "status": "running"})
    setattr(shell, f"{component_action}_session", operation)

    class FakeBooter:
        pass

    booter = FakeBooter()
    booter.shell = shell

    class FakeConfig:
        def get_config(self, umo):
            return {
                "provider_settings": {
                    "computer_use_runtime": "local",
                    "computer_use_require_admin": False,
                }
            }

    class FakeEvent:
        unified_msg_origin = "group-umo"
        role = "member"

        @staticmethod
        def get_sender_id():
            return "member-user"

    class FakeAstrContext:
        context = FakeConfig()
        event = FakeEvent()

    class FakeWrapper:
        context = FakeAstrContext()

    async def fake_get_booter(context, session_id):
        return booter

    monkeypatch.setattr(shell_tools, "get_booter", fake_get_booter)

    result = await ShellSessionTool().call(
        FakeWrapper(),
        action=action,
        session_id="sh_test",
        chars="input",
    )

    assert json.loads(result)["session_id"] == "sh_test"
    assert operation.await_args.kwargs["owner_id"] == "group-umo"
    assert operation.await_args.kwargs["requester_id"] == "member-user"
    assert operation.await_args.kwargs["requester_is_admin"] is False
    if component_action == "write":
        expected_chars = "input\n" if action == "write_line" else "input"
        assert operation.await_args.kwargs["chars"] == expected_chars


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

    result = await ExecuteShellTool().call(
        FakeWrapper(), command="chromium https://example.com"
    )

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
            env["MUTATED_BY_FAKE_SHELL"] = command
            calls.append(env)
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

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

    assert calls[0] is not calls[1]
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
            env["MUTATED_BY_FAKE_SHELL"] = command
            calls.append(env)
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

    class FakeBooter:
        shell = FakeShell()

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
    original_env = {"FOO": "bar"}

    await ExecuteShellTool().call(FakeWrapper(), command="first", env=original_env)

    assert original_env == {"FOO": "bar"}
    assert calls == [{"FOO": "bar", "MUTATED_BY_FAKE_SHELL": "first"}]


@pytest.mark.asyncio
async def test_execute_shell_avoids_double_background_for_detached_commands(
    monkeypatch,
):
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

    command = "nohup firefox >/tmp/astrbot-firefox.log 2>&1 &"
    result = await ExecuteShellTool().call(
        FakeWrapper(), command=command, background=True
    )

    assert json.loads(result)["success"] is True
    assert calls == [{"command": command, "background": False}]


@pytest.mark.asyncio
async def test_execute_shell_recognizes_commented_background_command(monkeypatch):
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

    command = "firefox & # already detached"
    result = await ExecuteShellTool().call(
        FakeWrapper(), command=command, background=True
    )

    assert json.loads(result)["success"] is True
    assert calls == [{"command": command, "background": False}]


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
async def test_execute_shell_reports_blank_exception_type(monkeypatch):
    from astrbot.core.tools.computer_tools import shell as shell_tools

    class BlankError(Exception):
        def __str__(self):
            return ""

    class FakeShell:
        async def exec(
            self, command, cwd=None, background=False, env=None, timeout=None
        ):
            raise BlankError()

    class FakeBooter:
        shell = FakeShell()

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

    result = await ExecuteShellTool().call(FakeWrapper(), command="firefox")

    assert result == "Error executing command: BlankError"


def test_firecrawl_tools_are_registered_as_builtin_tools():
    manager = FunctionToolManager()

    search_tool = manager.get_builtin_tool(FirecrawlWebSearchTool)
    extract_tool = manager.get_builtin_tool(FirecrawlExtractWebPageTool)

    assert search_tool.name == "web_search_firecrawl"
    assert extract_tool.name == "firecrawl_extract_web_page"
    assert manager.is_builtin_tool("web_search_firecrawl") is True
    assert manager.is_builtin_tool("firecrawl_extract_web_page") is True


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
