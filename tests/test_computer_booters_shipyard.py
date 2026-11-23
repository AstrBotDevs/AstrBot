"""Shipyard adapters preserve transport failures and normalize SDK envelopes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
    ShipyardBooter,
    ShipyardFileSystemWrapper,
    ShipyardShellWrapper,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,success,stdout,stderr",
    [
        ({"output": "old", "return_code": 0}, True, "old", ""),
        ({"success": True, "data": {"output": "new", "exit_code": 0}}, True, "new", ""),
        (
            {
                "success": False,
                "error": "request failed",
                "data": {"success": True, "error": None},
            },
            False,
            "",
            "request failed",
        ),
        ({"stdout": "", "exit_code": 2}, False, "", ""),
    ],
)
async def test_shell_normalizes_versions_without_hiding_failure(
    payload, success, stdout, stderr
):
    transport = SimpleNamespace(exec=AsyncMock(return_value=payload))
    result = await ShipyardShellWrapper(transport).exec(
        "echo test", cwd="/work", timeout=8
    )
    transport.exec.assert_awaited_once_with("echo test", timeout=8, cwd="/work")
    assert result["success"] is success
    assert result["stdout"] == stdout
    assert result["stderr"] == stderr


@pytest.mark.asyncio
async def test_shell_rejects_unsupported_mode_without_calling_sdk():
    transport = SimpleNamespace(exec=AsyncMock())
    result = await ShipyardShellWrapper(transport).exec("echo test", shell=False)
    assert result["success"] is False and result["exit_code"] == 2
    transport.exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_filesystem_preserves_read_window_and_flattens_payload():
    transport = SimpleNamespace(
        read_file=AsyncMock(
            return_value={"success": True, "data": {"content": "line 2"}}
        )
    )
    result = await ShipyardFileSystemWrapper(transport, SimpleNamespace()).read_file(
        "notes.txt", offset=1, limit=1
    )
    transport.read_file.assert_awaited_once_with(
        path="notes.txt", encoding="utf-8", offset=1, limit=1
    )
    assert result == {"success": True, "content": "line 2"}


def test_default_tool_list_changes_do_not_corrupt_cached_membership():
    tools = ShipyardBooter.get_default_tools()
    expected = {
        "astrbot_execute_shell",
        "astrbot_execute_ipython",
        "astrbot_upload_file",
        "astrbot_download_file",
    }
    assert {tool.name for tool in tools} == expected
    tools.clear()
    assert {tool.name for tool in ShipyardBooter.get_default_tools()} == expected
