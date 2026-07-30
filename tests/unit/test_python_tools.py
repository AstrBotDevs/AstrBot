import platform
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer.booters.local import LocalPythonComponent
from astrbot.core.tools.computer_tools.python import LocalPythonTool, PythonTool


def test_python_tool_description_contains_os():
    """测试 PythonTool 的描述中是否包含当前操作系统信息"""
    tool = PythonTool()
    current_os = platform.system()
    assert current_os in tool.description
    assert "IPython" in tool.description


def test_local_python_tool_description_contains_os():
    """测试 LocalPythonTool 的描述中是否包含当前操作系统信息和兼容性提示"""
    tool = LocalPythonTool()
    current_os = platform.system()
    assert current_os in tool.description
    assert "Python environment" in tool.description
    assert "system-compatible" in tool.description


@pytest.mark.asyncio
async def test_local_python_tool_uses_session_workspace(tmp_path, monkeypatch):
    """Local Python execution should use the same workspace as local shell."""
    tool = LocalPythonTool()
    python_exec = AsyncMock(
        return_value={"data": {"output": {"text": "ok", "images": []}, "error": ""}}
    )
    local_python = LocalPythonComponent()
    local_python.exec = python_exec
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.get_local_booter",
        lambda: SimpleNamespace(python=local_python),
    )

    async def fake_workspace_root_for_context(context):
        return tmp_path / context.context.event.unified_msg_origin.replace(":", "_")

    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root_for_context",
        fake_workspace_root_for_context,
    )

    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="admin",
        get_platform_name=lambda: "onebot",
    )
    context = ContextWrapper(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                get_config=lambda **_kwargs: {
                    "provider_settings": {"computer_use_require_admin": True}
                }
            ),
        ),
        tool_call_timeout=60,
    )

    await tool.call(context, code="print('ok')", timeout=30)

    workspace = tmp_path / "onebot_GroupMessage_12345"
    assert workspace.is_dir()
    python_exec.assert_awaited_once_with(
        "print('ok')",
        timeout=30,
        silent=False,
        cwd=str(workspace.resolve(strict=False)),
        sandboxed=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_name", ["linux", "darwin"])
async def test_local_member_python_uses_platform_sandbox(
    tmp_path,
    monkeypatch,
    platform_name,
):
    """Local member Python execution should require an OS sandbox."""
    from astrbot.core.tools.computer_tools import util as computer_util

    python_exec = AsyncMock(
        return_value={"data": {"output": {"text": "ok", "images": []}, "error": ""}}
    )
    local_python = LocalPythonComponent()
    local_python.exec = python_exec
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.get_local_booter",
        lambda: SimpleNamespace(python=local_python),
    )
    monkeypatch.setattr(computer_util.sys, "platform", platform_name)
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root_for_context",
        AsyncMock(return_value=tmp_path),
    )

    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="member",
        get_platform_name=lambda: "onebot",
    )
    context = ContextWrapper(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                get_config=lambda **_kwargs: {
                    "provider_settings": {
                        "computer_use_runtime": "local",
                        "computer_use_require_admin": False,
                    }
                }
            ),
        ),
        tool_call_timeout=60,
    )

    await LocalPythonTool().call(context, code="print('ok')", timeout=30)

    python_exec.assert_awaited_once_with(
        "print('ok')",
        timeout=30,
        silent=False,
        cwd=str(tmp_path.resolve(strict=False)),
        sandboxed=True,
    )


@pytest.mark.asyncio
async def test_local_member_python_is_denied_without_supported_sandbox(monkeypatch):
    """Local member Python execution should fail closed on other platforms."""
    from astrbot.core.tools.computer_tools import util as computer_util

    monkeypatch.setattr(computer_util.sys, "platform", "win32")
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.get_local_booter",
        lambda: pytest.fail("Local Python must not start without an OS sandbox"),
    )
    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="member",
    )
    context = ContextWrapper(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                get_config=lambda **_kwargs: {
                    "provider_settings": {
                        "computer_use_runtime": "local",
                        "computer_use_require_admin": False,
                    }
                }
            ),
        ),
        tool_call_timeout=60,
    )

    result = await LocalPythonTool().call(context, code="print('ok')")

    assert "Linux with bubblewrap or macOS with Seatbelt" in result
