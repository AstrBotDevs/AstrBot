"""A concrete shell adapter obeys the shared component calling convention."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters.cua import CuaShellComponent
from astrbot.core.astr_agent_runtime.computer.olayer.shell import ShellComponent


@pytest.mark.asyncio
async def test_shell_forwards_execution_options_and_normalizes_result():
    transport = AsyncMock(return_value={"stdout": "done", "stderr": "", "exit_code": 0})
    component: ShellComponent = CuaShellComponent(
        SimpleNamespace(shell=SimpleNamespace(exec=transport))
    )
    result = await component.exec(
        "echo done", cwd="/work", env={"LANG": "C"}, timeout=7, session_id="test"
    )
    transport.assert_awaited_once_with(
        "echo done", cwd="/work", env={"LANG": "C"}, timeout=7
    )
    assert result == {"stdout": "done", "stderr": "", "exit_code": 0, "success": True}


@pytest.mark.asyncio
async def test_non_shell_mode_fails_before_transport():
    transport = AsyncMock()
    component: ShellComponent = CuaShellComponent(
        SimpleNamespace(shell=SimpleNamespace(exec=transport))
    )
    result = await component.exec("echo done", shell=False)
    assert result["exit_code"] == 2 and result["success"] is False
    assert "only shell mode" in result["stderr"]
    transport.assert_not_awaited()
