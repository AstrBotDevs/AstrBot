"""Optional execution arguments and stable Bubblewrap workspace identity."""

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters import bwrap, local
from astrbot.core.astr_agent_runtime.computer.booters.cua import CuaPythonComponent
from astrbot.core.astr_agent_runtime.computer.booters.shipyard_neo import (
    NeoPythonComponent,
)


@pytest.fixture(params=["bwrap", "cua-python", "cua-shell", "neo"])
def python_backend(request, monkeypatch, tmp_path: Path):
    """Use strict transport signatures without requiring remote services."""
    calls: list[tuple[str, int | None]] = []

    def run(command, *, check, timeout, capture_output, text):
        assert check is False and capture_output is True and text is True
        calls.append((command[-1], timeout))
        return subprocess.CompletedProcess(command, 0, "backend-output\n", "")

    def cua_exec(code, *, timeout):
        async def response():
            calls.append((code, timeout))
            return {"stdout": "backend-output\n", "stderr": "", "exit_code": 0}

        return response()

    async def neo_exec(code):
        calls.append((code, None))
        return {"output": "backend-output\n", "error": "", "success": True}

    if request.param == "bwrap":
        monkeypatch.setattr(bwrap.subprocess, "run", run)
        component = bwrap.BwrapPythonComponent(bwrap.BwrapConfig(str(tmp_path)))
    elif request.param == "neo":
        component = NeoPythonComponent(
            SimpleNamespace(python=SimpleNamespace(exec=neo_exec))
        )
    else:
        component_name = "python" if request.param == "cua-python" else "shell"
        component = CuaPythonComponent(
            SimpleNamespace(**{component_name: SimpleNamespace(exec=cua_exec)})
        )
    return component, calls


@pytest.mark.asyncio
@pytest.mark.parametrize("silent", [False, True])
async def test_python_explicit_none_preserves_existing_execution(
    python_backend, silent: bool
) -> None:
    component, calls = python_backend
    code = "print('backend-output')"
    expected = await component.exec(code, kernel_id="kernel", timeout=7, silent=silent)

    actual = await component.exec(
        code, kernel_id="kernel", timeout=7, silent=silent, cwd=None
    )

    assert actual == expected
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert code in calls[0][0]
    assert calls[0][1] in (None, 7)


@pytest.mark.asyncio
@pytest.mark.parametrize("cwd", ["", "requested-workspace"])
async def test_python_rejects_unsupported_cwd_before_dispatch(
    python_backend, cwd: str
) -> None:
    component, calls = python_backend

    with pytest.raises(NotImplementedError, match="working directory"):
        await component.exec("raise AssertionError('must not execute')", cwd=cwd)

    assert calls == []


@pytest.mark.asyncio
async def test_local_shell_accepts_explicit_default_session(tmp_path: Path) -> None:
    shell = local.LocalShellComponent()

    result = await shell.exec(
        "echo default-session", cwd=str(tmp_path), timeout=5, session_id=None
    )

    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "default-session"
    assert result["stderr"] == ""
    assert shell._sessions == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["", "managed-session"])
@pytest.mark.parametrize("background", [False, True])
async def test_local_shell_rejects_session_ids_before_starting_a_process(
    monkeypatch, session_id: str, background: bool
) -> None:
    start = Mock(side_effect=AssertionError("A process must not be started"))
    monkeypatch.setattr(local.subprocess, "Popen", start)
    shell = local.LocalShellComponent()

    with pytest.raises(NotImplementedError, match="session_id"):
        await shell.exec(
            "echo must-not-run", session_id=session_id, background=background
        )

    start.assert_not_called()
    assert shell._sessions == {}


@pytest.mark.asyncio
async def test_default_session_preserves_local_shell_safety_check(monkeypatch) -> None:
    check = Mock(return_value=False)
    start = Mock(side_effect=AssertionError("A process must not be started"))
    monkeypatch.setattr(local, "_is_safe_command", check)
    monkeypatch.setattr(local.subprocess, "Popen", start)

    with pytest.raises(PermissionError, match="Blocked unsafe shell command"):
        await local.LocalShellComponent().exec("blocked command", session_id=None)

    check.assert_called_once_with("blocked command")
    start.assert_not_called()


@pytest.fixture
def successful_bwrap_probes(monkeypatch):
    """Keep host workspace tests independent of the sandbox runtime probes."""
    monkeypatch.setattr(bwrap.BwrapBooter, "available", AsyncMock(return_value=True))
    for component in (bwrap.BwrapShellComponent, bwrap.BwrapPythonComponent):
        monkeypatch.setattr(
            component,
            "exec",
            AsyncMock(return_value={"exit_code": 0, "stderr": ""}),
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Bubblewrap is Linux-only"
)
async def test_workspace_identity_survives_parent_symlink_retarget(
    monkeypatch, tmp_path: Path, successful_bwrap_probes
) -> None:
    """Host file access and cleanup must retain the workspace selected at boot."""
    original = tmp_path / "original"
    replacement = tmp_path / "replacement"
    original.mkdir()
    replacement.mkdir()
    alias = tmp_path / "temp-alias"
    alias.symlink_to(original, target_is_directory=True)
    workspace_name = "sandbox_workspace_stable"
    old_workspace = original / workspace_name
    new_workspace = replacement / workspace_name
    new_workspace.mkdir()
    (new_workspace / "marker").write_text("foreign", encoding="utf-8")
    monkeypatch.setattr(bwrap, "get_astrbot_temp_path", lambda: str(alias))
    booter = bwrap.BwrapBooter()
    try:
        await booter.boot("stable")
        assert (await booter.fs.write_file("marker", "original"))["success"]
        alias.unlink()
        alias.symlink_to(replacement, target_is_directory=True)

        assert (await booter.fs.write_file("marker", "retained"))["success"]

        assert (old_workspace / "marker").read_text(encoding="utf-8") == "retained"
        assert (new_workspace / "marker").read_text(encoding="utf-8") == "foreign"
    finally:
        await booter.shutdown()

    assert not old_workspace.exists()
    assert new_workspace.exists()
    assert alias.is_symlink()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Bubblewrap is Linux-only"
)
async def test_existing_workspace_symlink_never_transfers_cleanup_ownership(
    monkeypatch, tmp_path: Path, successful_bwrap_probes
) -> None:
    target = tmp_path / "unrelated"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    workspace = temp_root / "sandbox_workspace_existing"
    workspace.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(bwrap, "get_astrbot_temp_path", lambda: str(temp_root))
    booter = bwrap.BwrapBooter()
    startup_error = None
    try:
        await booter.boot("existing")
    except ValueError as exc:
        startup_error = exc
    finally:
        await booter.shutdown()

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert workspace.is_symlink()
    assert isinstance(startup_error, ValueError)
    assert "symbolic link" in str(startup_error)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
    reason="Requires Linux with Bubblewrap installed",
)
@pytest.mark.parametrize("readonly_root", [False, True])
async def test_real_bwrap_boots_under_a_symlinked_temp_parent(
    monkeypatch, tmp_path: Path, readonly_root: bool
) -> None:
    physical = tmp_path / "physical-temp"
    physical.mkdir()
    alias = tmp_path / "logical-temp"
    alias.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(bwrap, "get_astrbot_temp_path", lambda: str(alias))
    booter = bwrap.BwrapBooter(ro_binds=["/"] if readonly_root else None)
    workspace = physical / "sandbox_workspace_symlink"
    try:
        await booter.boot("symlink")
        result = await booter.shell.exec("pwd -P; printf retained > marker")
        assert result["exit_code"] == 0, result
        assert result["stdout"].strip() == str(workspace)
        assert (workspace / "marker").read_text(encoding="utf-8") == "retained"
    finally:
        await booter.shutdown()

    assert not workspace.exists()
    assert alias.is_symlink()
