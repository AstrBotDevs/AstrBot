from __future__ import annotations

import sys
import time
from pathlib import Path

import psutil
import pytest

from astrbot.core.astr_agent_runtime.computer.process_sandbox.base import (
    SandboxSpec,
    SandboxTimeoutError,
)
from astrbot.core.astr_agent_runtime.computer.process_sandbox.unix import (
    UnixProcessSandbox,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix process groups")


class PassthroughSandbox(UnixProcessSandbox):
    def _build_command(self, argv, workspace, spec, env):
        return argv


def test_search_sandbox_timeout_reaps_nested_child(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    code = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
    )
    child_pid = None
    try:
        with pytest.raises(SandboxTimeoutError):
            PassthroughSandbox().run(
                [sys.executable, "-c", code, str(pid_file)],
                SandboxSpec(workspace=tmp_path),
                timeout=1,
                output_limit=64,
            )
        child_pid = int(pid_file.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not psutil.pid_exists(child_pid):
                break
            if psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE:
                break
            time.sleep(0.02)
        assert not psutil.pid_exists(child_pid) or (
            psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE
        )
    finally:
        if child_pid is None and pid_file.exists():
            child_pid = int(pid_file.read_text())
        if child_pid is not None and psutil.pid_exists(child_pid):
            child = psutil.Process(child_pid)
            if child.status() != psutil.STATUS_ZOMBIE:
                child.kill()
                child.wait(timeout=5)


def test_search_sandbox_bounded_capture_shape_is_unchanged(tmp_path: Path):
    result = PassthroughSandbox().run(
        [sys.executable, "-c", "import sys; sys.stdout.write('abcdef')"],
        SandboxSpec(workspace=tmp_path),
        timeout=5,
        output_limit=3,
    )
    assert result.returncode == 0
    assert result.stdout == b"abc"
    assert result.stdout_limited
    assert result.stderr == b""
