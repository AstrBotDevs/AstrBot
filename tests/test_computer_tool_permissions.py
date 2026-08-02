import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
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
    return ContextWrapper(
        context=SimpleNamespace(context=config_holder, event=event)
    )


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
    assert resolved.filesystem_scope == "workspace"


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
