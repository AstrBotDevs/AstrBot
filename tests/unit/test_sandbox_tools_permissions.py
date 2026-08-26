import json
import time
from pathlib import Path
from types import SimpleNamespace

import mcp
import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.sandbox import (
    SandboxLifecycleTool,
    SandboxOperationTool,
    SandboxQueryTool,
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
    result = await SandboxOperationTool().call(
        _context(), "capture_screenshot", sandbox_id="sandbox-1"
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_tool_requires_admin_permission():
    result = await SandboxOperationTool().call(
        _context(),
        "copy_file",
        source_sandbox_id="source-1",
        source_path="/tmp/source.txt",
        target_sandbox_id="target-1",
        target_path="/tmp/target.txt",
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_handles_windows_target_filename(
    monkeypatch, tmp_path
):
    from astrbot.core.tools.computer_tools import sandbox as sandbox_tools

    copied: dict[str, str] = {}

    class SourceBooter:
        async def download_file(self, source_path, local_path):
            copied["source_path"] = source_path
            copied["local_path"] = local_path
            Path(local_path).write_text("payload", encoding="utf-8")

    class TargetBooter:
        async def upload_file(self, local_path, target_path):
            copied["upload_local_path"] = local_path
            copied["target_path"] = target_path
            return {"ok": True}

    class Manager:
        async def get_observer_booter_by_id(self, sandbox_id, *args, **kwargs):
            return SourceBooter() if sandbox_id == "source-1" else TargetBooter()

    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        sandbox_tools.computer_client,
        "sandbox_manager",
        Manager(),
    )

    result = await SandboxOperationTool().call(
        _admin_context_without_admin_requirement(),
        "copy_file",
        source_sandbox_id="source-1",
        source_path="/tmp/source.txt",
        target_sandbox_id="target-1",
        target_path=r"C:\Users\AstrBot\target.txt",
    )

    assert json.loads(result)["upload_result"] == {"ok": True}
    assert Path(copied["local_path"]).name.endswith("-target.txt")
    assert copied["target_path"] == r"C:\Users\AstrBot\target.txt"


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_includes_lease_metadata(
    monkeypatch, tmp_path
):
    from astrbot.core.tools.computer_tools import sandbox as sandbox_tools

    expires_at = time.time() + 600

    class SourceBooter:
        async def download_file(self, source_path, local_path):
            Path(local_path).write_text("payload", encoding="utf-8")

    class TargetBooter:
        async def upload_file(self, local_path, target_path):
            return {"ok": True}

    class Manager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "controller_session_id": "session-a",
                "lease_expires_at": expires_at,
            }
        )

        async def get_observer_booter_by_id(self, sandbox_id, *args, **kwargs):
            return SourceBooter() if sandbox_id == "source-1" else TargetBooter()

    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(sandbox_tools.computer_client, "sandbox_manager", Manager())

    result = await SandboxOperationTool().call(
        _sandbox_context(),
        "copy_file",
        source_sandbox_id="source-1",
        source_path="/tmp/source.txt",
        target_sandbox_id="target-1",
        target_path="/tmp/target.txt",
    )
    payload = json.loads(str(result))

    assert payload["lease"]["sandbox_id"] == "target-1"
    assert payload["lease"]["lease_expires_at"]
    assert payload["lease"]["lease_expires_in_seconds"] > 0
    assert payload["lease"]["auto_renew_interval_seconds"] == 600


@pytest.mark.asyncio
async def test_sandbox_operation_can_return_screenshot_image_to_llm(
    monkeypatch, tmp_path
):
    from astrbot.core.tools.computer_tools import sandbox as sandbox_tools

    class Gui:
        async def screenshot(self, path):
            Path(path).write_bytes(b"image")
            return {"base64": "aW1hZ2U=", "mime_type": "image/png"}

    class Booter:
        gui = Gui()

    class Manager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "controller_session_id": "session-a",
                "lease_expires_at": time.time() + 600,
            }
        )

        async def get_observer_booter_by_id(self, sandbox_id, *args, **kwargs):
            return Booter()

    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        sandbox_tools.computer_client,
        "sandbox_manager",
        Manager(),
    )

    result = await SandboxOperationTool().call(
        _admin_context_without_admin_requirement(),
        "capture_screenshot",
        sandbox_id="sandbox-1",
        return_image_to_llm=True,
    )

    assert isinstance(result, mcp.types.CallToolResult)
    assert isinstance(result.content[0], mcp.types.TextContent)
    assert isinstance(result.content[1], mcp.types.ImageContent)
    assert json.loads(result.content[0].text)["lease"]["sandbox_id"] == "sandbox-1"
    assert result.content[1].data == "aW1hZ2U="


@pytest.mark.asyncio
async def test_sensitive_sandbox_tools_require_strict_admin_permission():
    context = _member_context_with_sandbox_permissions(set_retention_policy=True)

    assert "Permission denied" in str(
        await SandboxLifecycleTool().call(context, "takeover", sandbox_id="sandbox-1")
    )
    assert "Permission denied" in str(
        await SandboxLifecycleTool().call(context, "destroy", sandbox_id="sandbox-1")
    )


@pytest.mark.asyncio
async def test_set_sandbox_retention_policy_tool_respects_admin_requirement():
    result = await SandboxLifecycleTool().call(
        _context(),
        "set_retention",
        retention_policy="persistent",
        sandbox_id="sandbox-1",
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

    assert "Permission denied" in str(
        await SandboxQueryTool().call(context, "list_sandboxes")
    )
    assert "Permission denied" in str(
        await SandboxQueryTool().call(context, "list_providers")
    )
    assert "Permission denied" in str(
        await SandboxQueryTool().call(context, "get_current")
    )


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

    assert "Permission denied" in str(
        await SandboxLifecycleTool().call(context, "create")
    )
    assert "Permission denied" in str(
        await SandboxLifecycleTool().call(
            context, "set_retention", retention_policy="persistent"
        )
    )
    assert "Permission denied" in str(
        await SandboxLifecycleTool().call(context, "destroy", sandbox_id="sandbox-1")
    )
    assert "Permission denied" in str(
        await SandboxLifecycleTool().call(context, "takeover", sandbox_id="sandbox-1")
    )


@pytest.mark.asyncio
async def test_member_takeover_sandbox_requires_explicit_permission(monkeypatch):
    calls = []

    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "session-a",
                "controller_session_id": None,
            },
            get_current_sandbox_id=lambda session_id: None,
        )

        async def takeover_sandbox(self, session_id, sandbox_id, **kwargs):
            calls.append((session_id, sandbox_id, kwargs))
            return {"sandbox_id": sandbox_id}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SandboxLifecycleTool().call(
        _member_context_with_sandbox_permissions(takeover=True),
        "takeover",
        sandbox_id="sandbox-1",
    )

    assert "sandbox-1" in str(result)
    assert calls


@pytest.mark.asyncio
async def test_member_takeover_or_destroy_rejects_other_idle_sandbox(monkeypatch):
    class FakeManager:
        registry = SimpleNamespace(
            get_sandbox=lambda sandbox_id: {
                "sandbox_id": sandbox_id,
                "owner_session_id": "session-b",
                "created_by_session_id": "session-b",
                "controller_session_id": None,
            },
            get_current_sandbox_id=lambda session_id: None,
        )

        async def takeover_sandbox(self, *args, **kwargs):
            raise AssertionError("takeover must be denied before manager call")

        async def destroy_sandbox(self, *args, **kwargs):
            raise AssertionError("destroy must be denied before manager call")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )
    context = _member_context_with_sandbox_permissions(takeover=True, destroy=True)

    takeover_result = await SandboxLifecycleTool().call(
        context,
        "takeover",
        sandbox_id="other-idle",
    )
    destroy_result = await SandboxLifecycleTool().call(
        context,
        "destroy",
        sandbox_id="other-idle",
    )

    assert "Permission denied" in str(takeover_result)
    assert "Permission denied" in str(destroy_result)


@pytest.mark.asyncio
async def test_create_sandbox_tool_reports_max_sandbox_limit(monkeypatch):
    class FakeManager:
        providers = {"generic": object()}

        async def create_sandbox(self, *args, **kwargs):
            raise RuntimeError("Sandbox limit reached. Maximum managed sandboxes: 10.")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    result = await SandboxLifecycleTool().call(
        _member_context_with_sandbox_permissions(create=True), "create"
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

    result = await SandboxQueryTool().call(
        _member_context_without_admin_requirement(), "list_sandboxes"
    )
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

    result = await SandboxQueryTool().call(
        _admin_context_without_admin_requirement(), "list_sandboxes"
    )
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

    result = await SandboxQueryTool().call(
        _member_context_without_admin_requirement(), "list_sandboxes"
    )

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

    result = await SandboxQueryTool().call(_sandbox_context(), "list_providers")
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

    result = await SandboxQueryTool().call(_sandbox_context(), "get_current")
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

    result = await SandboxLifecycleTool().call(
        _member_context_with_sandbox_permissions(create=True),
        "create",
        sandbox_name="Fresh",
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

    result = await SandboxLifecycleTool().call(
        _member_context_with_sandbox_permissions(create=True),
        "create",
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

    result = await SandboxLifecycleTool().call(
        _member_context_without_admin_requirement(),
        "switch",
        sandbox_id="default-idle",
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

    result = await SandboxLifecycleTool().call(
        _member_context_without_admin_requirement(),
        "switch",
        sandbox_id="ordinary-idle",
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

    result = await SandboxLifecycleTool().call(
        _member_context_without_admin_requirement(),
        "switch",
        sandbox_id="other-idle",
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

    result = await SandboxLifecycleTool().call(
        _member_context_without_admin_requirement(),
        "switch",
        sandbox_id="expired-id",
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

    result = await SandboxLifecycleTool().call(
        _member_context_without_admin_requirement(),
        "switch",
        sandbox_id="other-idle",
    )

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_keep_alive_sandbox_tool_renews_current_sandbox(monkeypatch):
    calls = []

    class FakeManager:
        async def renew_current_sandbox_lease(
            self, session_id, ttl_seconds=None, context=None
        ):
            calls.append((session_id, ttl_seconds, context))
            return {"sandbox_id": "sandbox-1", "lease_expires_at": time.time() + 3600}

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sandbox_manager", FakeManager()
    )

    context = _member_context_without_admin_requirement()
    result = await SandboxLifecycleTool().call(context, "renew_lease", ttl_seconds=3600)

    assert "sandbox-1" in str(result)
    assert calls == [("session-a", 3600, context.context.context)]

    payload = json.loads(str(result))
    assert payload["lease"]["sandbox_id"] == "sandbox-1"
    assert payload["lease"]["lease_expires_in_seconds"] > 0
    assert payload["lease"]["auto_renew_interval_seconds"] == 600


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
    result = await SandboxLifecycleTool().call(
        context, "set_retention", retention_policy="persistent"
    )
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

    result = await SandboxLifecycleTool().call(
        _member_context_with_sandbox_permissions(set_retention_policy=True),
        "set_retention",
        retention_policy="persistent",
        sandbox_id="sandbox-1",
    )

    assert "Permission denied" in str(result)
