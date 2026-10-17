import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer import process_sandbox
from astrbot.core.computer.booters import local
from astrbot.core.config import default as config_defaults
from astrbot.core.tools.computer_tools import fs, python, shell, util
from astrbot.core.tools.computer_tools.shipyard_neo.browser import BrowserExecTool
from astrbot.core.tools.computer_tools.shipyard_neo.neo_skills import (
    GetExecutionHistoryTool,
)
from astrbot.core.tools.computer_tools.util import (
    check_local_execution_permission,
    get_local_permission_policy,
)


@pytest.fixture(autouse=True)
def available_local_sandbox(monkeypatch):
    """Test configured policies independently of the test host's isolation."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {"status": "detected"})


class _FakeBrowser:
    async def exec(self, **kwargs):
        return {
            "ok": True,
            "cmd": kwargs["cmd"],
        }


class _FakeSandbox:
    async def get_execution_history(self, **kwargs):
        return {
            "items": [],
            "limit": kwargs["limit"],
        }


def _make_run_context(require_admin: bool, role: str = "member") -> ContextWrapper:
    config_holder = SimpleNamespace(
        get_config=lambda umo: {  # noqa: ARG005
            "provider_settings": {
                "computer_use_require_admin": require_admin,
            }
        }
    )
    event = SimpleNamespace(
        role=role,
        unified_msg_origin="qq_official:friend:user-1",
        get_sender_id=lambda: "user-1",
    )
    astr_ctx = SimpleNamespace(context=config_holder, event=event)
    return ContextWrapper(context=astr_ctx)


def _make_local_run_context(role: str, policy: dict) -> ContextWrapper:
    config_holder = SimpleNamespace(
        get_config=lambda umo: {  # noqa: ARG005
            "provider_settings": {
                "computer_use_runtime": "local",
                "computer_use_local_permissions": policy,
            }
        }
    )
    event = SimpleNamespace(
        role=role,
        unified_msg_origin="qq_official:friend:user-1",
        get_sender_id=lambda: "user-1",
    )
    return ContextWrapper(context=SimpleNamespace(context=config_holder, event=event))


def test_local_permission_policy_resolves_each_role_independently():
    policy = {
        "member": {
            "allow_execution": True,
            "allow_network": True,
            "filesystem_scope": "workspace",
        },
        "admin": {
            "allow_execution": True,
            "allow_network": False,
            "filesystem_scope": "host",
        },
    }

    member = get_local_permission_policy(_make_local_run_context("member", policy))
    admin = get_local_permission_policy(_make_local_run_context("admin", policy))

    assert member.allow_execution is True
    assert member.allow_network is True
    assert member.filesystem_scope == "workspace"
    assert member.requires_sandbox is True
    assert admin.allow_execution is True
    assert admin.allow_network is False
    assert admin.filesystem_scope == "host"
    assert admin.requires_sandbox is True


def test_local_permission_policy_treats_unknown_roles_as_members():
    policy = {
        "member": {
            "allow_execution": False,
            "allow_network": True,
            "filesystem_scope": "invalid",
        }
    }

    resolved = get_local_permission_policy(
        _make_local_run_context("unexpected", policy)
    )

    assert resolved.allow_execution is False
    assert resolved.allow_network is False
    assert (
        resolved.filesystem_scope
        == config_defaults.get_local_permission_defaults()["member"]["filesystem_scope"]
    )


@pytest.mark.parametrize("system", ["Windows", "Linux", "Darwin"])
@pytest.mark.parametrize("role", ["member", "admin", "unexpected"])
@pytest.mark.parametrize("permissions", [None, {}])
def test_local_permission_policy_platform_defaults(
    monkeypatch, system, role, permissions
):
    resolved = get_local_permission_policy(_make_local_run_context(role, permissions))

    assert resolved.allow_execution == (role == "admin")
    assert resolved.allow_network == (role == "admin")
    assert resolved.filesystem_scope == ("host" if role == "admin" else "workspace")
    assert resolved.requires_sandbox is False


@pytest.mark.parametrize("role", ["member", "admin", "unexpected"])
@pytest.mark.parametrize("allow_execution", [False, True])
@pytest.mark.parametrize("allow_network", [False, True])
def test_none_scope_disables_execution_and_network_for_only_the_selected_role(
    role, allow_execution, allow_network
):
    policy_role = "admin" if role == "admin" else "member"
    other_role = "member" if policy_role == "admin" else "admin"
    policy = {
        policy_role: {
            "filesystem_scope": "none",
            "allow_execution": allow_execution,
            "allow_network": allow_network,
        },
        other_role: {
            "filesystem_scope": "host",
            "allow_execution": True,
            "allow_network": True,
        },
    }

    resolved = get_local_permission_policy(_make_local_run_context(role, policy))
    other = get_local_permission_policy(_make_local_run_context(other_role, policy))

    assert resolved.filesystem_scope == "none"
    assert resolved.allow_execution is False
    assert resolved.allow_network is False
    assert other.filesystem_scope == "host"
    assert other.allow_execution is True
    assert other.allow_network is True


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize(
    ("tool", "kwargs"),
    [
        (fs.FileReadTool, {"path": "private.txt"}),
        (fs.FileWriteTool, {"path": "private.txt", "content": "changed"}),
        (fs.FileEditTool, {"path": "private.txt", "old": "secret", "new": "changed"}),
        (fs.GrepTool, {"pattern": "secret"}),
        (shell.LocalExecuteShellTool, {"command": "echo unexpected"}),
        (shell.ShellSessionTool, {"action": "list"}),
        (python.LocalPythonTool, {"code": "print('unexpected')"}),
    ],
)
async def test_none_scope_denies_all_local_tools_before_accessing_resources(
    monkeypatch, platform, role, tool, kwargs
):
    monkeypatch.setattr(process_sandbox, "sys", SimpleNamespace(platform=platform))
    booter = AsyncMock(side_effect=AssertionError("Denied tools must not get a booter"))
    workspace = AsyncMock(
        side_effect=AssertionError("Denied tools must not resolve a workspace")
    )
    local_booter = Mock(
        side_effect=AssertionError("Denied tools must not get a local booter")
    )
    sandbox = Mock(side_effect=AssertionError("Denied tools must not create a sandbox"))
    monkeypatch.setattr(fs, "get_booter", booter)
    monkeypatch.setattr(shell, "get_booter", booter)
    monkeypatch.setattr(python, "get_local_booter", local_booter)
    monkeypatch.setattr(fs, "workspace_root_for_context", workspace)
    monkeypatch.setattr(shell, "workspace_root_for_context", workspace)
    monkeypatch.setattr(python, "workspace_root_for_context", workspace)
    monkeypatch.setattr(util, "get_process_sandbox_status", sandbox)
    context = _make_local_run_context(
        role,
        {
            role: {
                "filesystem_scope": "none",
                "allow_execution": True,
                "allow_network": True,
            },
        },
    )

    result = await tool().call(context, **kwargs)

    assert "Permission denied" in result
    assert "Local Permission Policies" in result
    booter.assert_not_called()
    local_booter.assert_not_called()
    workspace.assert_not_called()
    sandbox.assert_not_called()


def test_local_permission_policy_denies_disabled_execution():
    policy = {
        "member": {
            "allow_execution": False,
            "allow_network": False,
            "filesystem_scope": "workspace",
        }
    }

    resolved, error = check_local_execution_permission(
        _make_local_run_context("member", policy),
        "Shell execution",
    )

    assert resolved is not None
    assert resolved.allow_execution is False
    assert error is not None
    assert "disabled by the Local permission policy" in error
    assert "user role (member)" in error
    assert "WebUI -> Config -> AI -> Capabilities" in error
    assert "Local Permission Policies" in error


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["detected", "missing", "unavailable", "unsupported"])
@pytest.mark.parametrize(
    "admin_scope,admin_execution,admin_network",
    [
        ("host", True, True),
        ("workspace", True, True),
        ("host", True, False),
        ("host", False, False),
        ("workspace", False, False),
        ("none", True, True),
    ],
)
@pytest.mark.parametrize(
    "tool,kwargs",
    [
        (shell.LocalExecuteShellTool, {"command": "echo forbidden"}),
        (shell.ShellSessionTool, {"action": "list"}),
        (python.LocalPythonTool, {"code": "print('forbidden')"}),
    ],
)
async def test_member_denial_offers_only_available_administrator_access(
    monkeypatch, status, admin_scope, admin_execution, admin_network, tool, kwargs
):
    """Offer promotion only when the effective admin policy allows execution."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {"status": status})
    policies = {
        "member": {"filesystem_scope": "workspace", "allow_execution": False, "allow_network": False},
        "admin": {"filesystem_scope": admin_scope, "allow_execution": admin_execution, "allow_network": admin_network},
    }
    original = json.dumps(policies, sort_keys=True)
    context = _make_local_run_context("member", policies)
    admin_can_execute = admin_execution and admin_scope != "none" and (
        (admin_scope == "host" and admin_network) or status == "detected"
    )

    result = await tool().call(context, **kwargs)

    assert "disabled by the Local permission policy" in result
    assert "Ask an AstrBot administrator" in result
    assert "Execute code" in result
    assert "Local Permission Policies" in result
    assert ("Administrator IDs" in result) == admin_can_execute
    assert ("user-1" in result) == admin_can_execute
    assert context.context.event.role == "member"
    assert get_local_permission_policy(context).allow_execution is False
    assert json.dumps(policies, sort_keys=True) == original


@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize("scope,execution", [("none", False), ("workspace", True)])
def test_other_denials_do_not_suggest_administrator_access(monkeypatch, role, scope, execution):
    """Keep isolation and disabled-file errors separate from execution grants."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {"status": "unsupported"})
    context = _make_local_run_context(role, {
        role: {"filesystem_scope": scope, "allow_execution": execution, "allow_network": False},
    })

    _, error = check_local_execution_permission(context, "Shell execution")

    assert error is not None
    assert "Administrator IDs" not in error
    assert ("Local isolation unavailable" in error) == execution


def test_admin_execution_denial_does_not_suggest_adding_administrator_id():
    """Already-admin callers only need their role policy changed."""
    context = _make_local_run_context("admin", {
        "admin": {"filesystem_scope": "host", "allow_execution": False},
    })

    _, error = check_local_execution_permission(context, "Python execution")

    assert "Execute code" in error
    assert "Administrator IDs" not in error
    assert "user role (admin)" in error


@pytest.mark.parametrize("role", ["member", "admin", "unexpected"])
@pytest.mark.parametrize("status", ["detected", "missing", "unavailable", "unsupported"])
@pytest.mark.parametrize("scope", ["none", "workspace", "host"])
@pytest.mark.parametrize("execution", [False, True])
@pytest.mark.parametrize("network", [False, True])
def test_local_policy_never_widens_saved_permissions(
    monkeypatch, role, status, scope, execution, network
):
    """Check every policy combination without granting permissions on failure."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {
        "status": status, "backend": "bubblewrap", "error": "probe diagnostic",
    })
    policy_role = "admin" if role == "admin" else "member"
    saved = {"allow_execution": execution, "allow_network": network, "filesystem_scope": scope}
    context = _make_local_run_context(role, {policy_role: saved.copy()})
    requires_isolation = scope != "none" and execution and (scope != "host" or not network)
    blocked = requires_isolation and status != "detected"

    resolved, error = check_local_execution_permission(context, "Shell execution")

    assert resolved.filesystem_scope == scope
    assert resolved.allow_execution == (scope != "none" and execution and not blocked)
    assert resolved.allow_network == (resolved.allow_execution and network)
    assert (resolved.execution_disabled_reason is not None) == blocked
    assert (error is not None) == (not resolved.allow_execution)
    if blocked:
        assert "Local isolation unavailable" in error
        assert "Do not bypass" not in error
        assert "Saved permissions have not been changed" not in error
        assert f"file access scope `{scope}`" in error
        assert f"current user role is `{policy_role}`" in error
    assert context.context.context.get_config("test")["provider_settings"]["computer_use_local_permissions"][policy_role] == saved


@pytest.mark.parametrize("status", ["missing", "unavailable", "unsupported"])
@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize("scope,execution,network", [("workspace", False, False), ("host", False, False), ("host", True, True)])
def test_permissions_that_do_not_need_isolation_are_preserved(
    monkeypatch, status, role, scope, execution, network
):
    """Unavailable isolation must not replace an already usable explicit policy."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {"status": status})
    resolved = get_local_permission_policy(_make_local_run_context(role, {
        role: {"filesystem_scope": scope, "allow_execution": execution, "allow_network": network},
    }))
    assert resolved.filesystem_scope == scope
    assert resolved.allow_execution is execution
    assert resolved.allow_network is network
    assert not resolved.requires_sandbox


@pytest.mark.parametrize("role", ["member", "admin"])
def test_unavailable_isolation_preserves_disabled_local_access(monkeypatch, role):
    """Explicitly disabled roles must not acquire Local access from fallback."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {"status": "missing"})
    context = _make_local_run_context(role, {role: {"filesystem_scope": "none"}})

    assert get_local_permission_policy(context).filesystem_scope == "none"
    assert check_local_execution_permission(context, "Shell execution")[1] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize(
    ("status", "detail", "recovery"),
    [
        ({"status": "missing", "backend": "bubblewrap"}, "bubblewrap is not installed", "Install bubblewrap"),
        ({"status": "unsupported", "backend": None}, "not supported on this platform", "Run AstrBot in an environment that supports Local process isolation"),
        ({"status": "unavailable", "backend": "seatbelt", "error": "SandboxTimeoutError"}, "seatbelt failed its startup probe: SandboxTimeoutError", "Restore macOS Seatbelt (`sandbox-exec`) availability"),
        ({"status": "missing", "backend": "seatbelt"}, "seatbelt is not installed", "Restore macOS Seatbelt (`sandbox-exec`) availability"),
        ({"status": "unavailable", "backend": "bubblewrap", "error": "Operation not permitted"}, "bubblewrap failed its startup probe: Operation not permitted", "Fix the bubblewrap startup failure"),
    ],
)
@pytest.mark.parametrize("scope,network", [("workspace", False), ("workspace", True), ("host", False)])
@pytest.mark.parametrize(
    "tool,kwargs",
    [
        (shell.LocalExecuteShellTool, {"command": "echo forbidden"}),
        (shell.ShellSessionTool, {"action": "list"}),
        (python.LocalPythonTool, {"code": "print('forbidden')"}),
    ],
)
async def test_isolation_failure_is_explained_to_llm_before_starting_tools(
    monkeypatch, role, status, detail, recovery, scope, network, tool, kwargs
):
    """Reject restricted execution with its actual cause for both roles."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: status)
    booter = Mock(side_effect=AssertionError("Denied execution must not get a booter"))
    monkeypatch.setattr(shell, "get_booter", booter)
    monkeypatch.setattr(shell, "get_local_booter", booter)
    monkeypatch.setattr(python, "get_local_booter", booter)
    context = _make_local_run_context(role, {
        role: {"allow_execution": True, "allow_network": network, "filesystem_scope": scope},
    })

    result = await tool().call(context, **kwargs)

    assert result.startswith("error: Local isolation unavailable.")
    assert detail in result
    assert "runtime is the local environment (`local`)" in result
    assert f"current user role is `{role}`" in result
    assert f"1. Keep the configured restrictions: {recovery}" in result
    assert "2. Allow execution without Local isolation:" in result
    assert ("set file access scope to `Entire environment`" in result) == (scope != "host")
    assert ("this also enables execution network access" in result) == (not network)
    assert "execution network access " + ("enabled" if network else "disabled") in result
    assert (
        "(Warning: this permits code execution with access to the entire environment "
        "and network, without isolation)."
    ) in result
    assert "Only an administrator should explicitly authorize this broader access" not in result
    assert "Local Permission Policies" in result
    assert ("Install bubblewrap" in result) == (
        status["status"] == "missing" and status["backend"] == "bubblewrap"
    )
    assert "Code execution is blocked" in result
    assert f"file access scope `{scope}`" in result
    assert "Saved permissions have not been changed" not in result
    assert "Do not bypass" not in result
    booter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize("tool_name", ["shell", "python"])
async def test_sandbox_launch_failure_never_retries_without_isolation(
    monkeypatch, tmp_path, role, tool_name
):
    """Fail closed when isolation breaks after a successful cached startup probe."""
    factory = Mock(side_effect=RuntimeError("Isolation backend stopped working"))
    monkeypatch.setattr(local, "create_process_sandbox", factory)
    direct_process = AsyncMock(side_effect=AssertionError("Must not launch directly"))
    direct_run = Mock(side_effect=AssertionError("Must not run directly"))
    monkeypatch.setattr(local.asyncio, "create_subprocess_shell", direct_process)
    monkeypatch.setattr(local.asyncio, "create_subprocess_exec", direct_process)
    monkeypatch.setattr(local.subprocess, "run", direct_run)
    context = _make_local_run_context(role, {
        role: {"allow_execution": True, "allow_network": False, "filesystem_scope": "workspace"},
    })
    context.context.event.get_sender_id = lambda: "user-1"
    context.tool_call_timeout = 30
    settings = context.context.context.get_config("test")
    settings["admins_id"] = ["user-1"]
    context.context.context.get_config = lambda umo: settings
    booter = SimpleNamespace(shell=local.LocalShellComponent(), python=local.LocalPythonComponent())
    monkeypatch.setattr(shell, "get_booter", AsyncMock(return_value=booter))
    monkeypatch.setattr(python, "get_local_booter", lambda: booter)
    monkeypatch.setattr(shell, "workspace_root_for_context", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(python, "workspace_root_for_context", AsyncMock(return_value=tmp_path))

    if tool_name == "shell":
        result = await shell.LocalExecuteShellTool().call(context, command="echo forbidden")
    else:
        result = await python.LocalPythonTool().call(context, code="print('forbidden')")

    assert result.startswith("Error executing")
    assert "Isolation backend stopped working" in result
    factory.assert_called_once()
    direct_process.assert_not_called()
    direct_run.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize("status", ["missing", "unavailable", "unsupported"])
@pytest.mark.parametrize("tool_name", ["shell", "python"])
async def test_default_execution_does_not_require_isolation(
    monkeypatch, tmp_path, role, status, tool_name
):
    """Keep role defaults usable without changing permissions on either role."""
    monkeypatch.setattr(util, "get_process_sandbox_status", lambda: {"status": status})
    sandbox_factory = Mock(side_effect=AssertionError("Fallback must not launch isolation"))
    monkeypatch.setattr(local, "create_process_sandbox", sandbox_factory)
    context = _make_local_run_context(role, config_defaults.get_local_permission_defaults("Linux"))
    settings = context.context.context.get_config("test")
    settings["admins_id"] = ["user-1"]
    context.context.context.get_config = lambda umo: settings
    context.context.event.get_sender_id = lambda: "user-1"
    context.context.event.get_platform_name = lambda: "test"
    context.tool_call_timeout = 30
    booter = SimpleNamespace(shell=local.LocalShellComponent(), python=local.LocalPythonComponent())
    get_booter = AsyncMock(return_value=booter)
    monkeypatch.setattr(shell, "get_booter", get_booter)
    monkeypatch.setattr(python, "get_local_booter", lambda: booter)
    workspace = AsyncMock(return_value=tmp_path)
    monkeypatch.setattr(shell, "workspace_root_for_context", workspace)
    monkeypatch.setattr(python, "workspace_root_for_context", workspace)
    try:
        if tool_name == "shell":
            result = await shell.LocalExecuteShellTool().call(context, command="echo legacy-fallback")
        else:
            result = await python.LocalPythonTool().call(context, code="print('legacy-fallback')")
        if role == "member":
            assert "Permission denied" in result
            workspace.assert_not_called()
            get_booter.assert_not_called()
        else:
            text = result if isinstance(result, str) else "".join(item.text for item in result.content)
            assert "legacy-fallback" in text
        sandbox_factory.assert_not_called()
    finally:
        await booter.shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_browser_tool_allows_non_admin_when_admin_requirement_disabled(
    monkeypatch,
):
    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(browser=_FakeBrowser())

    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.shipyard_neo.browser.get_booter",
        _fake_get_booter,
    )

    result = await BrowserExecTool().call(
        _make_run_context(require_admin=False),
        cmd="open https://example.com",
    )

    assert json.loads(result)["ok"] is True


@pytest.mark.asyncio
async def test_neo_skill_tool_allows_non_admin_when_admin_requirement_disabled(
    monkeypatch,
):
    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(
            bay_client=object(),
            sandbox=_FakeSandbox(),
        )

    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.shipyard_neo.neo_skills.get_booter",
        _fake_get_booter,
    )

    result = await GetExecutionHistoryTool().call(
        _make_run_context(require_admin=False),
        limit=5,
    )

    payload = json.loads(result)
    assert payload["items"] == []
    assert payload["limit"] == 5


@pytest.mark.asyncio
async def test_browser_tool_still_denies_non_admin_when_admin_requirement_enabled():
    result = await BrowserExecTool().call(
        _make_run_context(require_admin=True),
        cmd="open https://example.com",
    )

    assert "Permission denied" in result
    assert "Using browser tools is only allowed for admin users" in result
    assert "User's ID is: user-1" in result
