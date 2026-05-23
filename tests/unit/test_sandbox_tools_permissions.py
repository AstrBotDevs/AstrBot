import json
import time
from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.sandbox import (
    CopyFileBetweenSandboxesTool,
    CreateSandboxTool,
    DestroySandboxTool,
    GetCurrentSandboxTool,
    KeepAliveSandboxTool,
    ListSandboxesTool,
    ListSandboxProvidersTool,
    ScreenshotSandboxTool,
    SetSandboxRetentionPolicyTool,
    SwitchSandboxTool,
    TakeoverSandboxTool,
)


class FakeEvent:
    unified_msg_origin = "session-a"
    role = "member"

    def get_sender_id(self):
        return "user-a"


def _context():
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {"computer_use_require_admin": True}
        }
    )
    return ContextWrapper(
        context=SimpleNamespace(event=FakeEvent(), context=plugin_context)
    )


def _admin_context_without_admin_requirement():
    event = FakeEvent()
    event.role = "admin"
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {"computer_use_require_admin": False}
        }
    )
    return ContextWrapper(context=SimpleNamespace(event=event, context=plugin_context))


def _member_context_without_admin_requirement():
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {"computer_use_require_admin": False}
        }
    )
    return ContextWrapper(
        context=SimpleNamespace(event=FakeEvent(), context=plugin_context)
    )


def _member_context_with_sandbox_permissions(**permissions):
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {
                "computer_use_require_admin": False,
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "generic",
                    "member_permissions": dict(permissions),
                },
            }
        }
    )
    return ContextWrapper(
        context=SimpleNamespace(event=FakeEvent(), context=plugin_context)
    )


def _sandbox_context(default_provider: str = "generic"):
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {
                "computer_use_require_admin": False,
                "computer_use_runtime": "sandbox",
                "sandbox": {"booter": default_provider},
            }
        }
    )
    return ContextWrapper(
        context=SimpleNamespace(event=FakeEvent(), context=plugin_context)
    )


@pytest.mark.asyncio
async def test_screenshot_sandbox_tool_requires_admin_permission():
    result = await ScreenshotSandboxTool().call(_context(), "sandbox-1")

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_tool_requires_admin_permission():
    result = await CopyFileBetweenSandboxesTool().call(
        _context(),
        "source-1",
        "/tmp/source.txt",
        "target-1",
        "/tmp/target.txt",
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_sensitive_sandbox_tools_require_strict_admin_permission():
    context = _member_context_with_sandbox_permissions(set_retention_policy=True)

    assert "Permission denied" in str(
        await TakeoverSandboxTool().call(context, "sandbox-1")
    )
    assert "Permission denied" in str(
        await DestroySandboxTool().call(context, "sandbox-1")
    )


@pytest.mark.asyncio
async def test_set_sandbox_retention_policy_tool_respects_admin_requirement():
    result = await SetSandboxRetentionPolicyTool().call(
        _context(), "persistent", "sandbox-1"
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_readonly_sandbox_tools_respect_admin_requirement(monkeypatch):
    class FakeManager:
        def list_sandboxes(self):
            raise AssertionError("list must be denied")

        def get_current_sandbox(self, session_id):
            raise AssertionError("get current must be denied")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.list_sandbox_providers",
        lambda: (_ for _ in ()).throw(AssertionError("providers must be denied")),
    )
    context = _context()

    assert "Permission denied" in str(await ListSandboxesTool().call(context))
    assert "Permission denied" in str(await ListSandboxProvidersTool().call(context))
    assert "Permission denied" in str(await GetCurrentSandboxTool().call(context))


@pytest.mark.asyncio
async def test_member_sandbox_management_permissions_default_to_disabled(monkeypatch):
    class FakeManager:
        providers = {"generic": object()}
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "controller_session_id": "session-a",
            }
        )

        async def create_sandbox(self, *args, **kwargs):
            raise AssertionError("create must be denied by default")

        def set_sandbox_retention_policy(self, *args, **kwargs):
            raise AssertionError("retention changes must be denied by default")

        async def destroy_sandbox(self, *args, **kwargs):
            raise AssertionError("destroy must be denied by default")

        async def takeover_sandbox(self, *args, **kwargs):
            raise AssertionError("takeover must be denied by default")

        def get_current_sandbox(self, session_id):
            return {"current_sandbox_id": "sandbox-1"}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )
    context = _member_context_with_sandbox_permissions()

    assert "Permission denied" in str(await CreateSandboxTool().call(context))
    assert "Permission denied" in str(
        await SetSandboxRetentionPolicyTool().call(context, "persistent")
    )
    assert "Permission denied" in str(
        await DestroySandboxTool().call(context, "sandbox-1")
    )
    assert "Permission denied" in str(
        await TakeoverSandboxTool().call(context, "sandbox-1")
    )


@pytest.mark.asyncio
async def test_member_takeover_sandbox_requires_explicit_permission(monkeypatch):
    calls = []

    class FakeManager:
        async def takeover_sandbox(self, session_id, sandbox_id, **kwargs):
            calls.append((session_id, sandbox_id, kwargs))
            return {"sandbox_id": sandbox_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await TakeoverSandboxTool().call(
        _member_context_with_sandbox_permissions(takeover=True), "sandbox-1"
    )

    assert "sandbox-1" in str(result)
    assert calls


@pytest.mark.asyncio
async def test_create_sandbox_tool_reports_max_sandbox_limit(monkeypatch):
    class FakeManager:
        providers = {"generic": object()}

        async def create_sandbox(self, *args, **kwargs):
            raise RuntimeError("Sandbox limit reached. Maximum managed sandboxes: 10.")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await CreateSandboxTool().call(
        _member_context_with_sandbox_permissions(create=True)
    )

    assert "Error creating sandbox" in str(result)
    assert "Sandbox limit reached" in str(result)


@pytest.mark.asyncio
async def test_member_list_sandboxes_includes_all_sandboxes_with_status(
    monkeypatch,
):
    class FakeManager:
        def list_sandboxes(self):
            return [
                {
                    "sandbox_id": "owned",
                    "owner_session_id": "session-a",
                    "controller_session_id": None,
                },
                {
                    "sandbox_id": "current",
                    "owner_session_id": "session-b",
                    "controller_session_id": "session-a",
                },
                {
                    "sandbox_id": "other-idle",
                    "sandbox_name": "Other Idle",
                    "owner_session_id": "session-b",
                    "owner_user_id": "user-b",
                    "created_by_session_id": "session-b",
                    "created_by_user_id": "user-b",
                    "controller_session_id": None,
                    "connect_info": {"secret": "idle-secret"},
                    "status": "running",
                },
                {
                    "sandbox_id": "other-busy",
                    "sandbox_name": "Other Busy",
                    "owner_session_id": "session-c",
                    "owner_user_id": "user-c",
                    "created_by_session_id": "session-c",
                    "created_by_user_id": "user-c",
                    "controller_session_id": "session-c",
                    "controller_user_id": "user-c",
                    "connect_info": {"secret": "busy-secret"},
                    "status": "running",
                },
            ]

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await ListSandboxesTool().call(_member_context_without_admin_requirement())
    payload = json.loads(str(result))
    by_id = {item["sandbox_id"]: item for item in payload["sandboxes"]}

    assert "owned" in str(result)
    assert "current" in str(result)
    assert "other-idle" in str(result)
    assert "other-busy" in str(result)
    assert "idle-secret" not in str(result)
    assert "busy-secret" not in str(result)
    assert "session-c" not in str(result)
    assert "user-c" not in str(result)
    assert "session-b" not in str(result)
    assert "user-b" not in str(result)
    assert by_id["other-idle"]["access"]["status"] == "idle"
    assert by_id["other-idle"]["access"]["can_switch"] is True
    assert by_id["other-busy"]["access"]["status"] == "occupied"
    assert by_id["other-busy"]["access"]["can_switch"] is False


@pytest.mark.asyncio
async def test_list_sandboxes_includes_access_status_for_admin(monkeypatch):
    class FakeManager:
        def list_sandboxes(self):
            return [
                {
                    "sandbox_id": "current",
                    "controller_session_id": "session-a",
                    "controller_user_id": "user-a",
                    "connect_info": {"secret": "current-secret"},
                    "status": "running",
                },
                {
                    "sandbox_id": "occupied",
                    "controller_session_id": "session-b",
                    "controller_user_id": "user-b",
                    "lease_expires_at": time.time() + 60,
                    "connect_info": {"secret": "occupied-secret"},
                    "status": "running",
                },
                {
                    "sandbox_id": "idle",
                    "controller_session_id": None,
                    "connect_info": {"secret": "idle-secret"},
                    "status": "running",
                },
            ]

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await ListSandboxesTool().call(_admin_context_without_admin_requirement())
    payload = json.loads(str(result))
    by_id = {item["sandbox_id"]: item for item in payload["sandboxes"]}

    assert by_id["current"]["access"] == {
        "status": "current",
        "can_switch": True,
        "occupied": True,
    }
    assert by_id["occupied"]["access"] == {
        "status": "occupied",
        "can_switch": False,
        "occupied": True,
    }
    assert by_id["idle"]["access"] == {
        "status": "idle",
        "can_switch": True,
        "occupied": False,
    }
    assert by_id["occupied"]["connect_info"]["secret"] == "occupied-secret"


@pytest.mark.asyncio
async def test_sandbox_tools_use_current_computer_client_manager(monkeypatch):
    from astrbot.core.computer import computer_client

    class FakeManager:
        def list_sandboxes(self):
            return [{"sandbox_id": "dynamic-manager", "controller_session_id": None}]

    monkeypatch.setattr(computer_client, "sandbox_manager", FakeManager())

    result = await ListSandboxesTool().call(_member_context_without_admin_requirement())

    assert "dynamic-manager" in str(result)


@pytest.mark.asyncio
async def test_list_sandbox_providers_tool_exposes_loaded_provider_capabilities(
    monkeypatch,
):
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.list_sandbox_providers",
        lambda: [
            {
                "provider_id": "generic",
                "capabilities": ["shell"],
                "tool_names": ["generic_tool"],
                "system_prompt": "",
            }
        ],
    )

    result = await ListSandboxProvidersTool().call(_sandbox_context())
    payload = json.loads(str(result))

    assert payload["providers"] == [
        {
            "provider_id": "generic",
            "capabilities": ["shell"],
            "tool_names": ["generic_tool"],
            "system_prompt": "",
        }
    ]


@pytest.mark.asyncio
async def test_get_current_sandbox_tool_formats_agent_timestamps(monkeypatch):
    class FakeManager:
        def get_current_sandbox(self, session_id):
            return {
                "current_sandbox_id": "sandbox-1",
                "sandbox": {
                    "sandbox_id": "sandbox-1",
                    "retention_policy": "persistent",
                    "lease_expires_at": 1778557598.4646258,
                },
            }

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await GetCurrentSandboxTool().call(_sandbox_context())
    payload = json.loads(str(result))

    assert payload["sandbox"]["retention_policy"] == "persistent"
    assert payload["sandbox"]["lease_expires_at"] != 1778557598.4646258
    assert payload["sandbox"]["lease_expires_at"]


@pytest.mark.asyncio
async def test_create_sandbox_tool_defaults_to_configured_provider(monkeypatch):
    calls = []

    class FakeManager:
        providers = {"generic": object(), "other": object()}

        async def create_sandbox(
            self, plugin_context, session_id, provider_id, *, sandbox_name=None
        ):
            calls.append((plugin_context, session_id, provider_id, sandbox_name))
            return {"sandbox_id": "generic-1", "provider": provider_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await CreateSandboxTool().call(
        _member_context_with_sandbox_permissions(create=True), sandbox_name="Fresh"
    )
    payload = json.loads(str(result))

    assert payload["sandbox"]["provider"] == "generic"
    assert calls[0][2:] == ("generic", "Fresh")


@pytest.mark.asyncio
async def test_create_sandbox_tool_accepts_explicit_provider_id(monkeypatch):
    calls = []

    class FakeManager:
        providers = {"generic": object(), "other": object()}

        async def create_sandbox(
            self, plugin_context, session_id, provider_id, *, sandbox_name=None
        ):
            calls.append((plugin_context, session_id, provider_id, sandbox_name))
            return {"sandbox_id": "other-1", "provider": provider_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await CreateSandboxTool().call(
        _member_context_with_sandbox_permissions(create=True),
        sandbox_name="Fresh",
        provider_id="other",
    )
    payload = json.loads(str(result))

    assert payload["sandbox"]["provider"] == "other"
    assert calls[0][2:] == ("other", "Fresh")


@pytest.mark.asyncio
async def test_member_switch_sandbox_allows_idle_default_sandbox(monkeypatch):
    called = []

    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "dashboard",
                "controller_session_id": None,
                "is_default": True,
            }
        )

        async def switch_current_sandbox_checked(
            self, session_id, sandbox_id, **kwargs
        ):
            called.append((session_id, sandbox_id, kwargs))
            return {"sandbox_id": sandbox_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "default-idle"
    )

    assert "default-idle" in str(result)
    assert called


@pytest.mark.asyncio
async def test_member_switch_sandbox_allows_idle_dashboard_sandbox(monkeypatch):
    called = []

    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "dashboard",
                "controller_session_id": None,
                "is_default": False,
            }
        )

        async def switch_current_sandbox_checked(
            self, session_id, sandbox_id, **kwargs
        ):
            called.append((session_id, sandbox_id, kwargs))
            return {"sandbox_id": sandbox_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "ordinary-idle"
    )

    assert "ordinary-idle" in str(result)
    assert called


@pytest.mark.asyncio
async def test_member_switch_sandbox_allows_idle_sandbox_from_any_session(monkeypatch):
    called = []

    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "session-b",
                "controller_session_id": None,
                "is_default": False,
            }
        )

        async def switch_current_sandbox_checked(
            self, session_id, sandbox_id, **kwargs
        ):
            called.append((session_id, sandbox_id, kwargs))
            return {"sandbox_id": sandbox_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "other-idle"
    )

    assert "other-idle" in str(result)
    assert called


@pytest.mark.asyncio
async def test_member_switch_sandbox_allows_expired_lease_sandbox(monkeypatch):
    called = []

    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "session-b",
                "controller_session_id": "session-b",
                "lease_expires_at": time.time() - 1,
                "is_default": False,
            }
        )

        async def switch_current_sandbox_checked(
            self, session_id, sandbox_id, **kwargs
        ):
            called.append((session_id, sandbox_id, kwargs))
            return {"sandbox_id": sandbox_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "expired-id"
    )

    assert "expired-id" in str(result)
    assert called


@pytest.mark.asyncio
async def test_member_switch_sandbox_rejects_other_session_sandbox(monkeypatch):
    class FakeManager:
        def registry_get(self):
            return None

        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "session-b",
                "controller_session_id": "session-b",
            }
        )

        async def switch_current_sandbox_checked(self, *args, **kwargs):
            raise AssertionError("switch must not be called for another user's sandbox")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "other-idle"
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_keep_alive_sandbox_tool_renews_current_sandbox(monkeypatch):
    calls = []

    class FakeManager:
        async def renew_current_sandbox_lease(
            self, session_id, ttl_seconds=None, context=None
        ):
            calls.append((session_id, ttl_seconds))
            return {"sandbox_id": "sandbox-1", "lease_expires_at": 123.0}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await KeepAliveSandboxTool().call(
        _member_context_without_admin_requirement(), ttl_seconds=3600
    )

    assert "sandbox-1" in str(result)
    assert calls == [("session-a", 3600)]


@pytest.mark.asyncio
async def test_set_sandbox_retention_policy_tool_updates_current_sandbox(monkeypatch):
    calls = []

    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "controller_session_id": "session-a",
            }
        )

        def set_sandbox_retention_policy(
            self, plugin_context, session_id, sandbox_id, retention_policy, **kwargs
        ):
            calls.append((plugin_context, session_id, sandbox_id, retention_policy))
            return {"sandbox_id": sandbox_id, "retention_policy": retention_policy}

        def get_current_sandbox(self, session_id):
            return {"current_sandbox_id": "sandbox-1"}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    context = _member_context_with_sandbox_permissions(set_retention_policy=True)
    result = await SetSandboxRetentionPolicyTool().call(context, "persistent")
    payload = json.loads(str(result))

    assert payload["sandbox"]["retention_policy"] == "persistent"
    assert calls == [(context.context.context, "session-a", "sandbox-1", "persistent")]


@pytest.mark.asyncio
async def test_set_sandbox_retention_policy_tool_rejects_other_session_sandbox(
    monkeypatch,
):
    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "controller_session_id": "session-b",
                "lease_expires_at": time.time() + 60,
            }
        )

        def set_sandbox_retention_policy(self, *args, **kwargs):
            raise AssertionError("must not update another session's sandbox")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SetSandboxRetentionPolicyTool().call(
        _member_context_with_sandbox_permissions(set_retention_policy=True),
        "persistent",
        "sandbox-1",
    )

    assert "Permission denied" in str(result)
