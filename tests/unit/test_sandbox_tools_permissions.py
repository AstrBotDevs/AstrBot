import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.sandbox import (
    CopyFileBetweenSandboxesTool,
    CreateSandboxTool,
    DestroySandboxTool,
    KeepAliveSandboxTool,
    ListSandboxProvidersTool,
    ListSandboxesTool,
    ScreenshotSandboxTool,
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


def _member_context_without_admin_requirement():
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {"computer_use_require_admin": False}
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
    context = _member_context_without_admin_requirement()

    assert "Permission denied" in str(
        await ScreenshotSandboxTool().call(context, "sandbox-1")
    )
    assert "Permission denied" in str(
        await CopyFileBetweenSandboxesTool().call(
            context,
            "source-1",
            "/tmp/source.txt",
            "target-1",
            "/tmp/target.txt",
        )
    )
    assert "Permission denied" in str(
        await TakeoverSandboxTool().call(context, "sandbox-1")
    )
    assert "Permission denied" in str(
        await DestroySandboxTool().call(context, "sandbox-1")
    )


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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
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
async def test_list_sandbox_providers_tool_exposes_loaded_provider_capabilities(
    monkeypatch,
):
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.sandbox.list_sandbox_providers",
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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
    )

    result = await CreateSandboxTool().call(_sandbox_context(), sandbox_name="Fresh")
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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
    )

    result = await CreateSandboxTool().call(
        _sandbox_context(), sandbox_name="Fresh", provider_id="other"
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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "other-idle"
    )

    assert "other-idle" in str(result)
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
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
    )

    result = await SwitchSandboxTool().call(
        _member_context_without_admin_requirement(), "other-idle"
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_keep_alive_sandbox_tool_renews_current_sandbox(monkeypatch):
    calls = []

    class FakeManager:
        async def renew_current_sandbox_lease(self, session_id, ttl_seconds=None):
            calls.append((session_id, ttl_seconds))
            return {"sandbox_id": "sandbox-1", "lease_expires_at": 123.0}

    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.sandbox.sandbox_manager", FakeManager()
    )

    result = await KeepAliveSandboxTool().call(
        _member_context_without_admin_requirement(), ttl_seconds=3600
    )

    assert "sandbox-1" in str(result)
    assert calls == [("session-a", 3600)]
