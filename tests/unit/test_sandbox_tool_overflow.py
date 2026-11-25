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
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path


class _MinimalProvider(Provider):
    def __init__(self) -> None:
        super().__init__({}, {})

    def get_current_key(self) -> str:
        return "test_key"

    def set_key(self, key: str) -> None:
        _ = key

    async def get_models(self) -> list[str]:
        return ["test_model"]

    async def text_chat(self, **kwargs):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_sandbox_overflow_writer_writes_relative_path_and_validates_result(
    monkeypatch: pytest.MonkeyPatch,
):
    write_file = AsyncMock(
        return_value={
            "success": True,
            "path": ".astrbot_tool_overflow_call_1_deadbeef.txt",
        }
    )
    booter = SimpleNamespace(fs=SimpleNamespace(write_file=write_file))
    get_booter = AsyncMock(return_value=booter)
    monkeypatch.setattr(computer_client, "get_booter", get_booter)

    fake_context = cast(Any, SimpleNamespace())
    writer = create_sandbox_tool_result_overflow_writer(
        fake_context, "platform:group:123"
    )
    # Booter resolution must stay lazy until an overflow actually occurs.
    get_booter.assert_not_called()

    written_path = await writer("call_1_deadbeef.txt", "full payload")
    assert written_path == ".astrbot_tool_overflow_call_1_deadbeef.txt"
    get_booter.assert_awaited_once_with(fake_context, "platform:group:123")
    write_file.assert_awaited_once_with(
        path=".astrbot_tool_overflow_call_1_deadbeef.txt",
        content="full payload",
        mode="w",
        encoding="utf-8",
    )

    # Fallback to target_path when a booter omits the `path` key on success.
    write_file.return_value = {"success": True}
    assert (
        await writer("call_2_12345678.txt", "payload 2")
        == ".astrbot_tool_overflow_call_2_12345678.txt"
    )

    # Non-raising booter failures (Shipyard / Boxlite / CUA) must raise.
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
    local_booter = LocalBooter()
    monkeypatch.setattr(
        computer_client, "get_booter", AsyncMock(return_value=local_booter)
    )

    writer = create_sandbox_tool_result_overflow_writer(
        cast(Any, SimpleNamespace()), "platform:group:123"
    )
    with pytest.raises(RuntimeError, match="switched to local"):
        await writer("call_switch.txt", "untrusted payload")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["sandbox", "local"])
async def test_create_native_runner_configures_overflow_for_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: str,
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
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=AsyncMock(),
    )
    request = ProviderRequest(prompt="hello", func_tool=ToolSet([read_tool]))
    provider = _MinimalProvider()
    fake_context = cast(Any, SimpleNamespace())
    agent_context = cast(
        Any,
        SimpleNamespace(
            event=SimpleNamespace(unified_msg_origin="platform:user:42"),
        ),
    )

    runner = await create_native_runner(
        fake_context,
        provider,
        request,
        MainAgentBuildConfig(tool_call_timeout=60, computer_use_runtime=runtime),
        agent_context,
    )

    if runtime == "sandbox":
        assert runner.tool_result_overflow_dir is None
        assert runner.tool_result_overflow_writer is not None
        get_booter.assert_not_called()
        path = await runner.tool_result_overflow_writer("call_1.txt", "hello")
        assert path == ".astrbot_tool_overflow_call_1.txt"
        get_booter.assert_awaited_once_with(fake_context, "platform:user:42")
    else:
        assert runner.tool_result_overflow_dir == get_astrbot_system_tmp_path()
        assert runner.tool_result_overflow_writer is None


@pytest.mark.asyncio
async def test_create_native_runner_skips_overflow_when_read_tool_is_inactive():
    inactive_read_tool = FunctionTool(
        name="astrbot_file_read_tool",
        description="read file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=AsyncMock(),
        active=False,
    )
    request = ProviderRequest(prompt="hello", func_tool=ToolSet([inactive_read_tool]))
    runner = await create_native_runner(
        cast(Any, SimpleNamespace()),
        _MinimalProvider(),
        request,
        MainAgentBuildConfig(tool_call_timeout=60, computer_use_runtime="sandbox"),
        cast(
            Any,
            SimpleNamespace(
                event=SimpleNamespace(unified_msg_origin="platform:user:42"),
            ),
        ),
    )

    assert runner.read_tool is None
    assert runner.tool_result_overflow_dir is None
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
    workspace_dir.mkdir()
    other_cwd = tmp_path / "other_cwd"
    other_cwd.mkdir()

    write_calls: list[str] = []
    executed_codes: list[str] = []

    async def _write_file(
        *, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        _ = mode
        write_calls.append(path)
        assert not path.startswith("/")
        (workspace_dir / path).write_text(content, encoding=encoding, newline="\n")
        return {"success": True, "path": path}

    async def _python_exec(code: str) -> dict[str, Any]:
        executed_codes.append(code)
        mapped_code = code.replace("/workspace/", f"{workspace_dir.as_posix()}/")
        buf: list[str] = []
        exec(
            mapped_code,
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
    # Returned path stays relative to match Shipyard Neo's workspace-relative rule.
    read_path = await writer("call_chdir.txt", "line1\nline2\n")
    assert write_calls == [".astrbot_tool_overflow_call_chdir.txt"]
    assert read_path == ".astrbot_tool_overflow_call_chdir.txt"

    # Even when the sandbox kernel cwd has drifted away from /workspace,
    # read_file_tool_result resolves the relative path under workspace_root.
    monkeypatch.chdir(other_cwd)
    read_result = await read_file_tool_result(
        cast(Any, booter),
        local_mode=False,
        path=read_path,
        offset=0,
        limit=2,
    )
    assert read_result == "line1\nline2\n"
    assert all(
        "/workspace/.astrbot_tool_overflow_call_chdir.txt" in code
        for code in executed_codes
    )

    # Already-absolute POSIX paths must not be double-prefixed.
    executed_codes.clear()
    (workspace_dir / "absolute.txt").write_text(
        "abs-line\n", encoding="utf-8", newline="\n"
    )
    abs_result = await read_file_tool_result(
        cast(Any, booter),
        local_mode=False,
        path="/workspace/absolute.txt",
        offset=0,
        limit=1,
    )
    assert abs_result == "abs-line\n"
    assert all("/workspace/absolute.txt" in code for code in executed_codes)
    assert all("/workspace/workspace/" not in code for code in executed_codes)

    # Booters without a fixed workspace_root (legacy Shipyard, Boxlite, CUA)
    # must leave relative paths untouched rather than fabricating `/workspace/`.
    executed_codes.clear()
    (other_cwd / "rel.txt").write_text("rel-line\n", encoding="utf-8", newline="\n")
    unrooted_booter = SimpleNamespace(
        workspace_root=None,
        python=SimpleNamespace(exec=_python_exec),
    )
    rel_result = await read_file_tool_result(
        cast(Any, unrooted_booter),
        local_mode=False,
        path="rel.txt",
        offset=0,
        limit=1,
    )
    assert rel_result == "rel-line\n"
    assert all("/workspace/" not in code for code in executed_codes)
