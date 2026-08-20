import platform
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.python import LocalPythonTool, PythonTool
from tests.fixtures.auth import attach_authorized_tool_context


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
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root",
        lambda umo: tmp_path / umo.replace(":", "_"),
    )

    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="admin",
        get_platform_name=lambda: "onebot",
    )
    runtime = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": {}},
        computer_runtime=SimpleNamespace(
            get_local_booter=lambda: SimpleNamespace(
                python=SimpleNamespace(exec=python_exec)
            )
        ),
    )
    attach_authorized_tool_context(event, runtime, "tool.python_exec")
    context = ContextWrapper(
        context=SimpleNamespace(event=event, context=runtime),
        tool_call_timeout=60,
    )

    await tool.call(context, code="print('ok')", timeout_seconds=30)

    workspace = tmp_path / "onebot_GroupMessage_12345"
    assert workspace.is_dir()
    python_exec.assert_awaited_once_with(
        "print('ok')",
        timeout_seconds=30,
        silent=False,
        cwd=str(workspace.resolve(strict=False)),
    )


@pytest.mark.asyncio
async def test_local_python_tool_accepts_timeout_alias(tmp_path, monkeypatch):
    tool = LocalPythonTool()
    python_exec = AsyncMock(
        return_value={"data": {"output": {"text": "ok", "images": []}, "error": ""}}
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root",
        lambda umo: tmp_path / umo.replace(":", "_"),
    )

    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="admin",
        get_platform_name=lambda: "onebot",
    )
    runtime = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": {}},
        computer_runtime=SimpleNamespace(
            get_local_booter=lambda: SimpleNamespace(
                python=SimpleNamespace(exec=python_exec)
            )
        ),
    )
    attach_authorized_tool_context(event, runtime, "tool.python_exec")
    context = ContextWrapper(
        context=SimpleNamespace(event=event, context=runtime),
        tool_call_timeout=60,
    )

    await tool.call(context, code="print('ok')", timeout=12)

    python_exec.assert_awaited_once_with(
        "print('ok')",
        timeout_seconds=12,
        silent=False,
        cwd=str((tmp_path / "onebot_GroupMessage_12345").resolve(strict=False)),
    )
