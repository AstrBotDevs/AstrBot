import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import mcp

from astrbot.core.config.default import CONFIG_METADATA_3
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.provider.func_tool_manager import FunctionToolManager


class FakeContext:
    def __init__(self, config: dict):
        self._config = config

    def get_config(self, umo: str | None = None):
        return self._config


class FakeShell:
    def __init__(self):
        self.commands = []

    async def run(self, command: str, **kwargs):
        self.commands.append((command, kwargs))
        return {"stdout": "ok", "stderr": "", "exit_code": 0}


class ProcessShapeShell:
    async def run(self, command: str, **kwargs):
        return {"output": "shape-ok", "returncode": 0}


class FakePython:
    async def run(self, code: str, **kwargs):
        return {"output": "42", "error": ""}


class FakeFilesystem:
    def __init__(self):
        self.files = {}

    async def write_file(self, path: str, content: str):
        self.files[path] = content

    async def read_file(self, path: str):
        return self.files[path]

    async def delete(self, path: str):
        self.files.pop(path, None)

    async def list_dir(self, path: str):
        return [path]


class FakeMouse:
    def __init__(self):
        self.clicks = []

    async def click(self, x: int, y: int, button: str = "left"):
        self.clicks.append((x, y, button))
        return {"success": True}


class FakeKeyboard:
    def __init__(self):
        self.typed = []

    async def type(self, text: str):
        self.typed.append(text)
        return {"success": True}


class FakeSandbox:
    def __init__(self):
        self.shell = FakeShell()
        self.python = FakePython()
        self.filesystem = FakeFilesystem()
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    async def screenshot(self):
        return b"fake-png"


class SyncShell:
    def __init__(self, stdout: str = "ok"):
        self.commands = []
        self.stdout = stdout

    def run(self, command: str, **kwargs):
        self.commands.append((command, kwargs))
        return {"stdout": self.stdout, "stderr": "", "exit_code": 0}


class SyncPython:
    def run(self, code: str, **kwargs):
        return {"output": "sync", "error": ""}


def _agent_computer_use_items():
    return CONFIG_METADATA_3["ai_group"]["metadata"]["agent_computer_use"]["items"]


@pytest.mark.asyncio
async def test_get_booter_creates_cua_booter(monkeypatch):
    from astrbot.core.computer import computer_client

    created = []

    class FakeCuaBooter:
        def __init__(
            self,
            image: str,
            os_type: str,
            ttl: int,
            telemetry_enabled: bool,
            local: bool,
            api_key: str,
        ):
            created.append((image, os_type, ttl, telemetry_enabled, local, api_key))

        async def boot(self, session_id: str):
            self.session_id = session_id

        async def available(self):
            return True

    monkeypatch.setattr(computer_client, "_sync_skills_to_sandbox", lambda booter: asyncio.sleep(0))
    monkeypatch.setitem(computer_client.session_booter, "cua-test", None)
    computer_client.session_booter.pop("cua-test", None)
    monkeypatch.setattr(
        "astrbot.core.computer.booters.cua.CuaBooter",
        FakeCuaBooter,
        raising=False,
    )

    ctx = FakeContext(
        {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "cua",
                    "cua_image": "linux",
                    "cua_os_type": "linux",
                    "cua_ttl": 120,
                    "cua_telemetry_enabled": False,
                    "cua_local": True,
                    "cua_api_key": "",
                },
            }
        }
    )

    booter = await computer_client.get_booter(ctx, "cua-test")

    assert isinstance(booter, FakeCuaBooter)
    assert created == [("linux", "linux", 120, False, True, "")]


def test_cua_ephemeral_kwargs_include_local_when_supported():
    from astrbot.core.computer.booters.cua import CuaBooter

    def ephemeral(image, ttl=None, telemetry_enabled=None, local=None):
        return image, ttl, telemetry_enabled, local

    kwargs = CuaBooter(ttl=120, telemetry_enabled=False, local=True)._build_ephemeral_kwargs(
        ephemeral
    )

    assert kwargs == {"ttl": 120, "telemetry_enabled": False, "local": True}


def test_cua_ephemeral_kwargs_include_api_key_for_cloud_when_supported():
    from astrbot.core.computer.booters.cua import CuaBooter

    def ephemeral(image, local=None, api_key=None):
        return image, local, api_key

    kwargs = CuaBooter(local=False, api_key="sk-test")._build_ephemeral_kwargs(
        ephemeral
    )

    assert kwargs == {"local": False, "api_key": "sk-test"}


@pytest.mark.asyncio
async def test_cua_components_map_sdk_results(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
    )

    sandbox = FakeSandbox()

    shell_result = await CuaShellComponent(sandbox).exec("echo ok", cwd="/workspace")
    python_result = await CuaPythonComponent(sandbox).exec("print(42)")
    fs = CuaFileSystemComponent(sandbox)
    await fs.write_file("hello.txt", "hello")
    read_result = await fs.read_file("hello.txt")
    screenshot_path = tmp_path / "screen.png"
    gui = CuaGUIComponent(sandbox)
    screenshot_result = await gui.screenshot(str(screenshot_path))
    click_result = await gui.click(10, 20, button="right")
    type_result = await gui.type_text("hello")

    assert shell_result["stdout"] == "ok"
    assert python_result["data"]["output"]["text"] == "42"
    assert read_result["content"] == "hello"
    assert screenshot_path.read_bytes() == b"fake-png"
    assert screenshot_result["mime_type"] == "image/png"
    assert click_result["success"] is True
    assert type_result["success"] is True
    assert sandbox.mouse.clicks == [(10, 20, "right")]
    assert sandbox.keyboard.typed == ["hello"]


@pytest.mark.asyncio
async def test_cua_list_dir_returns_entries_list_for_shell_fallback():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    delattr(sandbox, "filesystem")

    result = await CuaFileSystemComponent(sandbox).list_dir(".")

    assert result["success"] is True
    assert result["entries"] == ["ok"]
    assert sandbox.shell.commands[0][0] == "ls -1 '.'"


@pytest.mark.asyncio
async def test_cua_write_file_shell_fallback_uses_python_base64_decoder():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    delattr(sandbox, "filesystem")

    await CuaFileSystemComponent(sandbox).write_file("hello.txt", "hello")

    command = sandbox.shell.commands[0][0]
    assert "python3 -c" in command
    assert "base64 -d" not in command


@pytest.mark.asyncio
async def test_cua_list_dir_shell_fallback_returns_filename_only_entries():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    sandbox.shell = SyncShell("alpha.txt\nfolder\n")
    delattr(sandbox, "filesystem")

    result = await CuaFileSystemComponent(sandbox).list_dir(".", show_hidden=True)

    assert result["entries"] == ["alpha.txt", "folder"]
    assert sandbox.shell.commands[0][0] == "ls -1A '.'"


@pytest.mark.asyncio
async def test_cua_shell_and_python_accept_sync_sdk_methods():
    from astrbot.core.computer.booters.cua import CuaPythonComponent, CuaShellComponent

    sandbox = FakeSandbox()
    sandbox.shell = SyncShell()
    sandbox.python = SyncPython()

    shell_result = await CuaShellComponent(sandbox).exec("echo ok")
    python_result = await CuaPythonComponent(sandbox).exec("print('ok')")

    assert shell_result["stdout"] == "ok"
    assert python_result["data"]["output"]["text"] == "sync"


@pytest.mark.asyncio
async def test_cua_shell_normalizes_output_returncode_shape():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    sandbox = FakeSandbox()
    sandbox.shell = ProcessShapeShell()

    result = await CuaShellComponent(sandbox).exec("echo ok")

    assert result == {
        "stdout": "shape-ok",
        "stderr": "",
        "exit_code": 0,
        "success": True,
    }


@pytest.mark.asyncio
async def test_cua_gui_reports_missing_mouse_or_keyboard():
    from astrbot.core.computer.booters.cua import CuaGUIComponent

    class SandboxWithoutGuiDevices:
        async def screenshot(self):
            return b"fake-png"

    gui = CuaGUIComponent(SandboxWithoutGuiDevices())

    with pytest.raises(RuntimeError, match="mouse.*click"):
        await gui.click(1, 2)

    with pytest.raises(RuntimeError, match="keyboard.*type"):
        await gui.type_text("hello")


def test_cua_capabilities_reflect_initialized_sandbox_gui_devices():
    from astrbot.core.computer.booters.cua import CuaBooter

    booter = CuaBooter()
    booter._sandbox = FakeSandbox()

    assert booter.capabilities == (
        "python",
        "shell",
        "filesystem",
        "gui",
        "screenshot",
        "mouse",
        "keyboard",
    )

    class ScreenshotOnlySandbox:
        async def screenshot(self):
            return b"fake-png"

    booter._sandbox = ScreenshotOnlySandbox()

    assert booter.capabilities == ("python", "shell", "filesystem", "gui", "screenshot")


@pytest.mark.asyncio
async def test_cua_shutdown_clears_cached_components():
    from astrbot.core.computer.booters.cua import CuaBooter

    closed = []

    class FakeSandboxContext:
        async def __aexit__(self, exc_type, exc, tb):
            closed.append(True)

    booter = CuaBooter()
    booter._sandbox = FakeSandbox()
    booter._sandbox_cm = FakeSandboxContext()
    booter._shell = object()
    booter._python = object()
    booter._fs = object()
    booter._gui = object()

    await booter.shutdown()

    assert closed == [True]
    assert await booter.available() is False
    assert booter._shell is None
    assert booter._python is None
    assert booter._fs is None
    assert booter._gui is None


def test_cua_tools_are_registered_as_builtin_tools():
    from astrbot.core.tools.computer_tools.cua import (
        CuaKeyboardTypeTool,
        CuaMouseClickTool,
        CuaScreenshotTool,
    )

    manager = FunctionToolManager()

    assert manager.get_builtin_tool(CuaScreenshotTool).name == "astrbot_cua_screenshot"
    assert manager.get_builtin_tool(CuaMouseClickTool).name == "astrbot_cua_mouse_click"
    assert manager.get_builtin_tool(CuaKeyboardTypeTool).name == "astrbot_cua_keyboard_type"


def test_cua_runtime_tools_are_available_to_handoffs():
    manager = FunctionToolManager()

    tools = FunctionToolExecutor._get_runtime_computer_tools("sandbox", manager, "cua")

    assert "astrbot_cua_screenshot" in tools
    assert "astrbot_cua_mouse_click" in tools
    assert "astrbot_cua_keyboard_type" in tools


def test_runtime_tool_selection_treats_none_booter_as_empty():
    manager = FunctionToolManager()

    tools = FunctionToolExecutor._get_runtime_computer_tools("sandbox", manager, None)

    assert "astrbot_execute_shell" in tools
    assert "astrbot_cua_screenshot" not in tools


def test_runtime_tool_selection_normalizes_cua_booter_case():
    manager = FunctionToolManager()

    tools = FunctionToolExecutor._get_runtime_computer_tools("sandbox", manager, "CUA")

    assert "astrbot_cua_screenshot" in tools


def test_cua_is_exposed_in_sandbox_config_metadata():
    items = _agent_computer_use_items()
    booter = items["provider_settings.sandbox.booter"]

    assert "cua" in booter["options"]
    assert "CUA" in booter["labels"]
    assert "provider_settings.sandbox.cua_image" in items
    assert "provider_settings.sandbox.cua_os_type" in items
    assert "provider_settings.sandbox.cua_ttl" in items
    assert "provider_settings.sandbox.cua_telemetry_enabled" in items
    assert "provider_settings.sandbox.cua_local" in items
    assert "provider_settings.sandbox.cua_api_key" in items
    assert items["provider_settings.sandbox.cua_api_key"]["condition"][
        "provider_settings.sandbox.cua_local"
    ] is False


@pytest.mark.asyncio
async def test_screenshot_tool_returns_image_and_sends_file(monkeypatch, tmp_path):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaScreenshotTool

    sent_messages = []

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        async def send(self, message):
            sent_messages.append(message)

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {
                "provider_settings": {
                    "computer_use_runtime": "sandbox",
                    "computer_use_require_admin": True,
                    "sandbox": {"booter": "cua"},
                }
            }
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGUI:
        async def screenshot(self, path: str):
            Path(path).write_bytes(b"fake-png")
            return {
                "success": True,
                "path": path,
                "mime_type": "image/png",
                "base64": base64.b64encode(b"fake-png").decode(),
            }

    class FakeBooter:
        gui = FakeGUI()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(cua_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(cua_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotTool().call(FakeWrapper(), send_to_user=True)

    assert isinstance(result, mcp.types.CallToolResult)
    image_parts = [part for part in result.content if part.type == "image"]
    text_parts = [part for part in result.content if part.type == "text"]
    payload = json.loads(text_parts[0].text)
    assert image_parts == []
    assert "base64" not in payload
    assert Path(payload["path"]).exists()
    assert sent_messages


@pytest.mark.asyncio
async def test_screenshot_tool_can_opt_in_to_llm_image_content(monkeypatch, tmp_path):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaScreenshotTool

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        async def send(self, message):
            pass

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext({"provider_settings": {"computer_use_require_admin": True}})

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGUI:
        async def screenshot(self, path: str):
            Path(path).write_bytes(b"fake-png")
            return {
                "success": True,
                "path": path,
                "mime_type": "image/png",
                "base64": base64.b64encode(b"fake-png").decode(),
            }

    class FakeBooter:
        gui = FakeGUI()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(cua_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(cua_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotTool().call(
        FakeWrapper(), send_to_user=False, return_image_to_llm=True
    )

    image_parts = [part for part in result.content if part.type == "image"]
    text_parts = [part for part in result.content if part.type == "text"]
    payload = json.loads(text_parts[0].text)
    assert image_parts[0].data == base64.b64encode(b"fake-png").decode()
    assert "base64" not in payload


@pytest.mark.asyncio
async def test_cua_tools_return_permission_error_without_gui_lookup(monkeypatch):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import (
        CuaKeyboardTypeTool,
        CuaMouseClickTool,
        CuaScreenshotTool,
    )

    sent_messages = []

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "member"

        async def send(self, message):
            sent_messages.append(message)

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext({"provider_settings": {}})

    class FakeWrapper:
        context = FakeAstrContext()

    async def fail_gui_lookup(context):
        raise AssertionError("GUI lookup should not run after permission failure")

    monkeypatch.setattr(cua_tools, "check_admin_permission", lambda *args: "denied")
    monkeypatch.setattr(cua_tools, "_get_gui_component", fail_gui_lookup)

    assert await CuaScreenshotTool().call(FakeWrapper()) == "denied"
    assert await CuaMouseClickTool().call(FakeWrapper(), x=1, y=2) == "denied"
    assert await CuaKeyboardTypeTool().call(FakeWrapper(), text="hello") == "denied"
    assert sent_messages == []
