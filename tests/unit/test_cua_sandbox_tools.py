import base64
import json
import os
import time
from pathlib import Path

import mcp
import pytest

from astrbot.core.provider.func_tool_manager import FunctionToolManager

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class FakeContext:
    def __init__(self, config: dict):
        self._config = config

    def get_config(self, umo: str | None = None):
        return self._config


def _wrapper(session_id: str = "session-a", role: str = "admin"):
    event_role = role

    class FakeEvent:
        unified_msg_origin = session_id
        role = event_role

        async def send(self, message):
            return None

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {
                "provider_settings": {
                    "computer_use_runtime": "sandbox",
                    "computer_use_require_admin": True,
                    "sandbox": {"booter": "cua", "cua_image": "linux"},
                }
            }
        )

    class FakeWrapper:
        context = FakeAstrContext()

    return FakeWrapper()


@pytest.mark.asyncio
async def test_non_admin_can_list_and_switch_existing_sandbox(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools.cua_sandbox import (
        CuaListSandboxesTool,
        CuaSwitchSandboxTool,
    )

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-default",
        sandbox_name="Default sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="admin",
        owner_session_id="admin-session",
        connect_info={"name": "Default sandbox"},
        is_default=True,
    )
    monkeypatch.setattr(computer_client, "cua_registry", registry)

    user_context = _wrapper("webchat:FriendMessage:user", role="member")
    list_result = json.loads(await CuaListSandboxesTool().call(user_context))
    switch_result = json.loads(
        await CuaSwitchSandboxTool().call(user_context, sandbox_id="sb-default")
    )

    assert list_result["success"] is True
    assert switch_result["success"] is True
    assert registry.get_current_sandbox_id("webchat:FriendMessage:user") == "sb-default"


@pytest.mark.asyncio
async def test_cua_sandbox_tools_create_list_switch_release_takeover_destroy(
    monkeypatch,
    tmp_path: Path,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools.cua_sandbox import (
        CuaCreateSandboxTool,
        CuaDestroySandboxTool,
        CuaGetCurrentSandboxTool,
        CuaListSandboxesTool,
        CuaReleaseSandboxTool,
        CuaSwitchSandboxTool,
        CuaTakeoverSandboxTool,
    )

    class FakeBooter:
        def __init__(self, sandbox_id: str):
            self.sandbox_id = sandbox_id
            self.shutdowns = 0

        async def available(self):
            return True

        async def shutdown(self):
            self.shutdowns += 1

    created = []

    async def fake_boot_managed(ctx, session_id, sandbox_id, cua_kwargs):
        created.append((session_id, sandbox_id, cua_kwargs["image"]))
        return FakeBooter(sandbox_id)

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    monkeypatch.setattr(computer_client, "_boot_managed_cua_sandbox", fake_boot_managed)
    computer_client.session_booter.clear()

    create_result = json.loads(
        await CuaCreateSandboxTool().call(_wrapper(), sandbox_name="worker-a")
    )
    sandbox_id = create_result["sandbox"]["sandbox_id"]

    assert create_result["success"] is True
    assert create_result["sandbox"]["sandbox_name"] == "worker-a"
    assert created == [("session-a", sandbox_id, "linux")]

    list_result = json.loads(await CuaListSandboxesTool().call(_wrapper()))
    assert [item["sandbox_id"] for item in list_result["sandboxes"]] == [sandbox_id]

    current_result = json.loads(await CuaGetCurrentSandboxTool().call(_wrapper()))
    assert current_result["current_sandbox_id"] == sandbox_id

    switch_result = json.loads(
        await CuaSwitchSandboxTool().call(_wrapper(), sandbox_id=sandbox_id)
    )
    assert switch_result["success"] is True

    release_result = json.loads(await CuaReleaseSandboxTool().call(_wrapper()))
    assert release_result["success"] is True

    registry.acquire_lease(
        sandbox_id=sandbox_id,
        session_id="session-b",
        user_id="session-b",
        ttl=300,
    )
    takeover_result = json.loads(
        await CuaTakeoverSandboxTool().call(_wrapper(), sandbox_id=sandbox_id)
    )
    assert takeover_result["success"] is True
    assert registry.get_sandbox(sandbox_id)["controller_session_id"] == "session-a"

    destroy_result = json.loads(
        await CuaDestroySandboxTool().call(_wrapper(), sandbox_id=sandbox_id)
    )
    assert destroy_result["success"] is True
    assert registry.get_sandbox(sandbox_id) is None
    assert registry.get_current_sandbox_id("session-a") is None
    assert sandbox_id not in computer_client.session_booter


@pytest.mark.asyncio
async def test_cua_screenshot_sandbox_observes_busy_sandbox_without_takeover(
    monkeypatch,
    tmp_path: Path,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.booters.cua import CuaGUIComponent
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools import cua_sandbox as sandbox_tools
    from astrbot.core.tools.computer_tools.cua_sandbox import CuaScreenshotSandboxTool

    class FakeSandbox:
        async def screenshot(self):
            return {"base64": base64.b64encode(_PNG_BYTES).decode()}

    class FakeBooter:
        gui = CuaGUIComponent(FakeSandbox())

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-busy",
        sandbox_name="busy",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-a",
        owner_session_id="session-a",
        controller_user_id="user-a",
        controller_session_id="session-a",
        lease_expires_at=time.time() + 60,
        last_used_at=1.0,
        connect_info={"name": "busy", "local": True},
    )
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-busy"] = FakeBooter()
    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotSandboxTool().call(
        _wrapper("session-b"),
        sandbox_id="sb-busy",
        send_to_user=False,
    )

    record = registry.get_sandbox("sb-busy")
    assert isinstance(result, mcp.types.CallToolResult)
    assert record["controller_session_id"] == "session-a"
    assert record["last_used_at"] != 1.0


def test_cua_sandbox_tools_are_registered_as_builtin_tools():
    manager = FunctionToolManager()

    for tool_name in (
        "astrbot_list_sandboxes",
        "astrbot_get_current_sandbox",
        "astrbot_create_sandbox",
        "astrbot_switch_sandbox",
        "astrbot_release_sandbox",
        "astrbot_takeover_sandbox",
        "astrbot_destroy_sandbox",
        "astrbot_screenshot_sandbox",
        "astrbot_copy_file_between_sandboxes",
    ):
        assert manager.is_builtin_tool(tool_name) is True


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_uses_temp_relay_and_cleans_up(
    monkeypatch,
    tmp_path: Path,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools import cua_sandbox as sandbox_tools
    from astrbot.core.tools.computer_tools.cua_sandbox import (
        CuaCopyFileBetweenSandboxesTool,
    )

    operations = []
    relay_paths = []

    class SourceBooter:
        async def available(self):
            return True

        async def download_file(self, remote_path: str, local_path: str):
            operations.append(("download", remote_path, Path(local_path).name))
            relay_paths.append(local_path)
            Path(local_path).write_text("relay-content", encoding="utf-8")

    class TargetBooter:
        async def available(self):
            return True

        async def upload_file(self, path: str, file_name: str) -> dict:
            operations.append(
                ("upload", Path(path).read_text(encoding="utf-8"), file_name)
            )
            return {"success": True, "file_path": file_name}

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    for sandbox_id in ("sb-source", "sb-target"):
        registry.upsert_sandbox(
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_id,
            booter_type="cua",
            provider="cua",
            managed=True,
            created_by_astrbot=True,
            owner_user_id="session-a",
            owner_session_id="session-a",
            controller_user_id="session-a" if sandbox_id == "sb-target" else None,
            controller_session_id="session-a" if sandbox_id == "sb-target" else None,
            lease_expires_at=time.time() + 60 if sandbox_id == "sb-target" else None,
            connect_info={"name": sandbox_id, "local": True},
        )
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-source"] = SourceBooter()
    computer_client.session_booter["sb-target"] = TargetBooter()
    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = json.loads(
        await CuaCopyFileBetweenSandboxesTool().call(
            _wrapper("session-a"),
            source_sandbox_id="sb-source",
            source_path="/tmp/input.txt",
            target_sandbox_id="sb-target",
            target_path="/tmp/output.txt",
        )
    )

    assert result["success"] is True
    assert operations == [
        ("download", "/tmp/input.txt", Path(relay_paths[0]).name),
        ("upload", "relay-content", "/tmp/output.txt"),
    ]
    assert relay_paths
    assert all(not Path(path).exists() for path in relay_paths)


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_closes_relay_file_descriptor(
    monkeypatch,
    tmp_path: Path,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools import cua_sandbox as sandbox_tools
    from astrbot.core.tools.computer_tools.cua_sandbox import (
        CuaCopyFileBetweenSandboxesTool,
    )

    class SourceBooter:
        async def available(self):
            return True

        async def download_file(self, remote_path: str, local_path: str):
            Path(local_path).write_text("relay-content", encoding="utf-8")

    class TargetBooter:
        async def available(self):
            return True

        async def upload_file(self, path: str, file_name: str) -> dict:
            return {"success": True, "file_path": file_name}

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    for sandbox_id in ("sb-source", "sb-target"):
        registry.upsert_sandbox(
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_id,
            booter_type="cua",
            provider="cua",
            managed=True,
            created_by_astrbot=True,
            owner_user_id="session-a",
            owner_session_id="session-a",
            controller_user_id="session-a" if sandbox_id == "sb-target" else None,
            controller_session_id="session-a" if sandbox_id == "sb-target" else None,
            lease_expires_at=time.time() + 60 if sandbox_id == "sb-target" else None,
            connect_info={"name": sandbox_id, "local": True},
        )
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-source"] = SourceBooter()
    computer_client.session_booter["sb-target"] = TargetBooter()
    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    closed = []
    original_mkstemp = computer_client.tempfile.mkstemp
    original_close = computer_client.os.close

    def tracked_mkstemp(*args, **kwargs):
        fd, path = original_mkstemp(*args, **kwargs)
        closed.append(False)

        def tracked_close(close_fd):
            if close_fd == fd:
                closed[0] = True
            return original_close(close_fd)

        monkeypatch.setattr(computer_client.os, "close", tracked_close)
        return fd, path

    monkeypatch.setattr(computer_client.tempfile, "mkstemp", tracked_mkstemp)

    result = json.loads(
        await CuaCopyFileBetweenSandboxesTool().call(
            _wrapper("session-a"),
            source_sandbox_id="sb-source",
            source_path="/tmp/input.txt",
            target_sandbox_id="sb-target",
            target_path="/tmp/output.txt",
        )
    )

    assert result["success"] is True
    assert closed == [True]


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_cleans_temp_file_on_upload_failure(
    monkeypatch,
    tmp_path: Path,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools import cua_sandbox as sandbox_tools
    from astrbot.core.tools.computer_tools.cua_sandbox import (
        CuaCopyFileBetweenSandboxesTool,
    )

    relay_paths = []

    class SourceBooter:
        async def available(self):
            return True

        async def download_file(self, remote_path: str, local_path: str):
            relay_paths.append(local_path)
            Path(local_path).write_text("relay-content", encoding="utf-8")

    class FailingTargetBooter:
        async def available(self):
            return True

        async def upload_file(self, path: str, file_name: str) -> dict:
            raise RuntimeError("upload failed")

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    for sandbox_id in ("sb-source", "sb-target"):
        registry.upsert_sandbox(
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_id,
            booter_type="cua",
            provider="cua",
            managed=True,
            created_by_astrbot=True,
            owner_user_id="session-a",
            owner_session_id="session-a",
            controller_user_id="session-a" if sandbox_id == "sb-target" else None,
            controller_session_id="session-a" if sandbox_id == "sb-target" else None,
            lease_expires_at=time.time() + 60 if sandbox_id == "sb-target" else None,
            connect_info={"name": sandbox_id, "local": True},
        )
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-source"] = SourceBooter()
    computer_client.session_booter["sb-target"] = FailingTargetBooter()
    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaCopyFileBetweenSandboxesTool().call(
        _wrapper("session-a"),
        source_sandbox_id="sb-source",
        source_path="/tmp/input.txt",
        target_sandbox_id="sb-target",
        target_path="/tmp/output.txt",
    )

    assert "upload failed" in result
    assert relay_paths
    assert all(not Path(path).exists() for path in relay_paths)


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_rejects_busy_target_without_fallback(
    monkeypatch,
    tmp_path: Path,
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.cua_registry import CuaSandboxRegistry
    from astrbot.core.tools.computer_tools import cua_sandbox as sandbox_tools
    from astrbot.core.tools.computer_tools.cua_sandbox import (
        CuaCopyFileBetweenSandboxesTool,
    )

    class Booter:
        async def available(self):
            return True

    registry = CuaSandboxRegistry(storage_path=tmp_path / "registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-source",
        sandbox_name="source",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "source", "local": True},
    )
    registry.upsert_sandbox(
        sandbox_id="sb-target",
        sandbox_name="target",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-b",
        owner_session_id="session-b",
        controller_user_id="session-b",
        controller_session_id="session-b",
        lease_expires_at=time.time() + 60,
        connect_info={"name": "target", "local": True},
    )
    monkeypatch.setattr(computer_client, "cua_registry", registry)
    computer_client.session_booter.clear()
    computer_client.session_booter["sb-source"] = Booter()
    computer_client.session_booter["sb-target"] = Booter()
    monkeypatch.setattr(sandbox_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaCopyFileBetweenSandboxesTool().call(
        _wrapper("session-a"),
        source_sandbox_id="sb-source",
        source_path="/tmp/input.txt",
        target_sandbox_id="sb-target",
        target_path="/tmp/output.txt",
    )

    assert "busy" in result
    assert os.listdir(tmp_path) == []
