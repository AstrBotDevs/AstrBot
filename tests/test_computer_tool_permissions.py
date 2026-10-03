import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer import process_sandbox
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
    monkeypatch.setattr(
        config_defaults, "platform", SimpleNamespace(system=lambda: system)
    )
    resolved = get_local_permission_policy(_make_local_run_context(role, permissions))

    assert resolved.allow_execution == (role == "admin")
    assert resolved.allow_network == (role == "admin")
    assert resolved.filesystem_scope == (
        ("host" if role == "admin" else "none") if system == "Windows" else "workspace"
    )
    assert resolved.requires_sandbox == (system != "Windows" or role != "admin")


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
    monkeypatch.setattr(util, "create_process_sandbox", sandbox)
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
    assert "WebUI -> Config -> Normal Config" in error
    assert "Local Permission Policies" in error


@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.parametrize(
    ("allow_network", "filesystem_scope"),
    [(False, "host"), (False, "workspace"), (True, "workspace")],
)
def test_windows_local_execution_requires_a_full_trust_policy(
    monkeypatch, role, allow_network, filesystem_scope
):
    """Windows rejects restricted policies and allows explicit full trust."""
    monkeypatch.setattr(process_sandbox, "sys", SimpleNamespace(platform="win32"))
    restricted = {
        role: {
            "allow_execution": True,
            "allow_network": allow_network,
            "filesystem_scope": filesystem_scope,
        }
    }
    full_trust = {
        role: {
            "allow_execution": True,
            "allow_network": True,
            "filesystem_scope": "host",
        }
    }

    _, restricted_error = check_local_execution_permission(
        _make_local_run_context(role, restricted),
        "Shell execution",
    )
    full_policy, full_error = check_local_execution_permission(
        _make_local_run_context(role, full_trust),
        "Shell execution",
    )

    assert restricted_error is not None
    assert "No Local process sandbox backend" in restricted_error
    assert "Third-party sandbox" in restricted_error
    assert "Computer Use Runtime" in restricted_error
    assert full_error is None
    assert full_policy is not None
    assert full_policy.requires_sandbox is False


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
