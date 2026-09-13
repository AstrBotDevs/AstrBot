import platform
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
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
@pytest.mark.parametrize(
    "runtime_settings",
    [
        {},
        {"computer_use_runtime": "none"},
        {"computer_use_runtime": "sandbox"},
        {"computer_use_runtime": "invalid"},
        {"computer_use_runtime": None},
    ],
)
@pytest.mark.parametrize("role", ["member", "admin"])
async def test_local_python_tool_rejects_nonlocal_runtime(
    runtime_settings, role, monkeypatch
):
    """Reject retained local tools before accessing the host, regardless of role."""
    get_local_booter = MagicMock()
    workspace_root = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.get_local_booter", get_local_booter
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root_for_context",
        workspace_root,
    )
    context = ContextWrapper(
        context=SimpleNamespace(
            event=SimpleNamespace(
                unified_msg_origin="onebot:FriendMessage:user123", role=role
            ),
            context=SimpleNamespace(
                get_config=lambda **_kwargs: {
                    "provider_settings": {
                        **runtime_settings,
                        "computer_use_require_admin": False,
                    }
                }
            ),
        )
    )

    result = await LocalPythonTool().call(context, code="print('ok')")

    get_local_booter.assert_not_called()
    workspace_root.assert_not_awaited()
    assert result == "Error executing code: only local runtime is supported."


@pytest.mark.asyncio
async def test_local_python_tool_uses_session_workspace(tmp_path, monkeypatch):
    """Local Python execution should use the same workspace as local shell."""
    tool = LocalPythonTool()
    python_exec = AsyncMock(
        return_value={"data": {"output": {"text": "ok", "images": []}, "error": ""}}
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.get_local_booter",
        lambda: SimpleNamespace(python=SimpleNamespace(exec=python_exec)),
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
                    "provider_settings": {
                        "computer_use_runtime": "local",
                        "computer_use_require_admin": True,
                    }
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
    )
