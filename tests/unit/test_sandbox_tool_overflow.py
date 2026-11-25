"""Unit tests for sandbox tool-result overflow writing and workspace-root reads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_runtime.computer import computer_client
from astrbot.core.astr_agent_runtime.computer.booters.cua import CuaBooter
from astrbot.core.astr_agent_runtime.computer.booters.local import LocalBooter
from astrbot.core.astr_agent_runtime.computer.booters.shipyard import ShipyardBooter
from astrbot.core.astr_agent_runtime.computer.booters.shipyard_neo import (
    ShipyardNeoBooter,
)
from astrbot.core.astr_agent_runtime.computer.file_read_utils import (
    read_file_tool_result,
)
from astrbot.core.astr_agent_runtime.execution import (
    create_native_runner,
    create_sandbox_tool_result_overflow_writer,
)
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path


@pytest.mark.asyncio
async def test_sandbox_overflow_writer_writes_and_validates_result(
    monkeypatch: pytest.MonkeyPatch,
):
    write_file = AsyncMock(
        return_value={
            "success": True,
            "path": ".astrbot_tool_overflow_call_1_deadbeef.txt",
        }
    )
    get_booter = AsyncMock(
        return_value=SimpleNamespace(fs=SimpleNamespace(write_file=write_file))
    )
    monkeypatch.setattr(computer_client, "get_booter", get_booter)

    fake_context = cast(Any, SimpleNamespace())
    writer = create_sandbox_tool_result_overflow_writer(
        fake_context, "platform:group:123"
    )
    get_booter.assert_not_called()

    assert (
        await writer("call_1_deadbeef.txt", "full payload")
        == ".astrbot_tool_overflow_call_1_deadbeef.txt"
    )
    get_booter.assert_awaited_once_with(fake_context, "platform:group:123")
    write_file.assert_awaited_once_with(
        path=".astrbot_tool_overflow_call_1_deadbeef.txt",
        content="full payload",
        mode="w",
        encoding="utf-8",
    )

    write_file.return_value = {"success": True}
    assert (
        await writer("call_2.txt", "payload 2") == ".astrbot_tool_overflow_call_2.txt"
    )

    for failure_result, expected_error in (
        ({"success": False, "error": "permission denied"}, "permission denied"),
        ({"success": False, "stderr": "python3 not found"}, "python3 not found"),
        ({"success": False, "message": "disk quota reached"}, "disk quota reached"),
        ({"success": False}, "unknown sandbox filesystem write error"),
    ):
        write_file.return_value = failure_result
        with pytest.raises(RuntimeError, match=expected_error):
            await writer("call_fail.txt", "payload")


@pytest.mark.asyncio
async def test_sandbox_overflow_writer_rejects_local_booter_after_runtime_switch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        computer_client, "get_booter", AsyncMock(return_value=LocalBooter())
    )

    writer = create_sandbox_tool_result_overflow_writer(
        cast(Any, SimpleNamespace()), "platform:group:123"
    )
    with pytest.raises(RuntimeError, match="switched to local"):
        await writer("call_switch.txt", "untrusted payload")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "read_tool_active"),
    [("sandbox", True), ("local", True), ("sandbox", False)],
)
async def test_create_native_runner_configures_overflow_for_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: str,
    read_tool_active: bool,
):
    get_booter = AsyncMock(
        return_value=SimpleNamespace(
            fs=SimpleNamespace(write_file=AsyncMock(return_value={"success": True}))
        )
    )
    monkeypatch.setattr(computer_client, "get_booter", get_booter)

    read_tool = FunctionTool(
        name="astrbot_file_read_tool",
        description="read file",
        parameters={},
        handler=AsyncMock(),
        active=read_tool_active,
    )
    fake_context = cast(Any, SimpleNamespace())
    provider = cast(
        Any, SimpleNamespace(provider_config={}, get_model=lambda: "test_model")
    )
    runner = await create_native_runner(
        fake_context,
        provider,
        ProviderRequest(prompt="hello", func_tool=ToolSet([read_tool])),
        MainAgentBuildConfig(tool_call_timeout=60, computer_use_runtime=runtime),
        cast(
            Any,
            SimpleNamespace(
                event=SimpleNamespace(unified_msg_origin="platform:user:42")
            ),
        ),
    )

    if not read_tool_active:
        assert runner.read_tool is None
        assert runner.tool_result_overflow_dir is None
        assert runner.tool_result_overflow_writer is None
    elif runtime == "sandbox":
        assert runner.tool_result_overflow_dir is None
        assert runner.tool_result_overflow_writer is not None
        get_booter.assert_not_called()
        assert (
            await runner.tool_result_overflow_writer("call_1.txt", "hello")
            == ".astrbot_tool_overflow_call_1.txt"
        )
        get_booter.assert_awaited_once_with(fake_context, "platform:user:42")
    else:
        assert runner.tool_result_overflow_dir == get_astrbot_system_tmp_path()
        assert runner.tool_result_overflow_writer is None


@pytest.mark.asyncio
async def test_file_read_resolves_booter_workspace_root_after_kernel_cwd_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    assert ShipyardNeoBooter.workspace_root == "/workspace"
    assert ShipyardBooter.workspace_root is None
    assert CuaBooter.workspace_root is None

    workspace_dir = tmp_path / "workspace"
    other_cwd = tmp_path / "other_cwd"
    workspace_dir.mkdir()
    other_cwd.mkdir()
    executed_codes: list[str] = []

    async def _write_file(
        *, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        _ = mode
        assert not path.startswith("/")
        (workspace_dir / path).write_text(content, encoding=encoding, newline="\n")
        return {"success": True, "path": path}

    async def _python_exec(code: str) -> dict[str, Any]:
        executed_codes.append(code)
        buf: list[str] = []
        exec(
            code.replace("/workspace/", f"{workspace_dir.as_posix()}/"),
            {"print": lambda *args, **_kw: buf.append(" ".join(map(str, args)))},
        )
        return {
            "success": True,
            "data": {"output": {"text": "\n".join(buf)}, "error": ""},
        }

    booter = SimpleNamespace(
        workspace_root="/workspace",
        fs=SimpleNamespace(write_file=_write_file),
        python=SimpleNamespace(exec=_python_exec),
    )
    monkeypatch.setattr(computer_client, "get_booter", AsyncMock(return_value=booter))

    writer = create_sandbox_tool_result_overflow_writer(
        cast(Any, SimpleNamespace()), "platform:group:99"
    )
    read_path = await writer("call_chdir.txt", "line1\nline2\n")
    assert read_path == ".astrbot_tool_overflow_call_chdir.txt"

    # Relative reads survive Python kernel cwd drift under workspace_root.
    monkeypatch.chdir(other_cwd)
    assert (
        await read_file_tool_result(
            cast(Any, booter), local_mode=False, path=read_path, offset=0, limit=2
        )
        == "line1\nline2\n"
    )
    assert all(f"/workspace/{read_path}" in code for code in executed_codes)

    # Absolute POSIX paths are not double-prefixed.
    executed_codes.clear()
    (workspace_dir / "abs.txt").write_text("abs\n", encoding="utf-8", newline="\n")
    assert (
        await read_file_tool_result(
            cast(Any, booter),
            local_mode=False,
            path="/workspace/abs.txt",
            offset=0,
            limit=1,
        )
        == "abs\n"
    )
    assert all("/workspace/workspace/" not in code for code in executed_codes)

    # Booters without a fixed workspace_root leave relative paths untouched.
    executed_codes.clear()
    (other_cwd / "rel.txt").write_text("rel\n", encoding="utf-8", newline="\n")
    unrooted = SimpleNamespace(
        workspace_root=None, python=SimpleNamespace(exec=_python_exec)
    )
    assert (
        await read_file_tool_result(
            cast(Any, unrooted), local_mode=False, path="rel.txt", offset=0, limit=1
        )
        == "rel\n"
    )
    assert all("/workspace/" not in code for code in executed_codes)
