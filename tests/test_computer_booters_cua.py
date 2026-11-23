"""CUA lifecycle, health checks, and GUI payloads without a live desktop."""

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters.cua import (
    CuaBooter,
    CuaGUIComponent,
    _screenshot_to_bytes,
)


@pytest.mark.asyncio
async def test_unbooted_cua_is_unavailable_and_shutdown_is_idempotent():
    booter = CuaBooter(telemetry_enabled=False, local=True)
    assert await booter.available() is False
    assert booter.capabilities == ("python", "shell", "filesystem")
    await booter.shutdown()
    await booter.shutdown()
    assert await booter.available() is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,available",
    [
        ({"stdout": "_astrbot_cua_ok_\n", "exit_code": 0}, True),
        ({"stdout": "wrong marker", "exit_code": 0}, False),
        ({"stdout": "_astrbot_cua_ok_", "exit_code": 1}, False),
    ],
)
async def test_cua_health_requires_success_and_probe_marker(reply, available):
    booter = CuaBooter(telemetry_enabled=False)
    shell = SimpleNamespace(exec=AsyncMock(return_value=reply))
    booter._runtime = SimpleNamespace(shell=shell)
    assert await booter.available() is available
    shell.exec.assert_awaited_once_with("echo _astrbot_cua_ok_", timeout=10)


@pytest.mark.asyncio
async def test_cua_health_propagates_cancellation():
    booter = CuaBooter(telemetry_enabled=False)
    booter._runtime = SimpleNamespace(
        shell=SimpleNamespace(exec=AsyncMock(side_effect=asyncio.CancelledError))
    )
    with pytest.raises(asyncio.CancelledError):
        await booter.available()


@pytest.mark.asyncio
async def test_gui_forwards_input_and_materializes_screenshot(tmp_path):
    data = b"deterministic screenshot bytes"
    sandbox = SimpleNamespace(
        screenshot=AsyncMock(return_value=data),
        mouse=SimpleNamespace(click=AsyncMock(return_value={"success": True})),
        keyboard=SimpleNamespace(
            type=AsyncMock(return_value={"success": True}),
            press_key=AsyncMock(return_value={"success": True}),
        ),
    )
    gui = CuaGUIComponent(sandbox)
    assert await gui.click(12, 34, button="right") == {"success": True}
    assert await gui.type_text("hello") == {"success": True}
    assert await gui.press_key("ENTER") == {"success": True}
    sandbox.mouse.click.assert_awaited_once_with(12, 34, button="right")
    sandbox.keyboard.type.assert_awaited_once_with("hello")
    sandbox.keyboard.press_key.assert_awaited_once_with("ENTER")
    target = tmp_path / "nested" / "screen.png"
    result = await gui.screenshot(str(target))
    assert target.read_bytes() == data
    assert base64.b64decode(result["base64"]) == data
    assert result["path"] == str(target) and result["mime_type"] == "image/png"


@pytest.mark.parametrize(
    "payload",
    [
        b"image",
        bytearray(b"image"),
        "aW1hZ2U=",
        "data:image/png;base64,aW1hZ2U=",
        {"base64": "aW1hZ2U="},
    ],
)
def test_screenshot_accepts_supported_sdk_payloads(payload):
    assert _screenshot_to_bytes(payload) == b"image"


def test_screenshot_rejects_unknown_object():
    with pytest.raises(TypeError, match="Unsupported CUA screenshot"):
        _screenshot_to_bytes(object())
