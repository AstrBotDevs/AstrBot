"""Tests for the single-instance guard in main.py.

The guard lives inside the ``if __name__ == "__main__"`` block, so each test runs
main.py as a real subprocess. ``ASTRBOT_ROOT`` always points at ``tmp_path``, so no
real user directory is touched.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from filelock import FileLock

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"

# Exit code the harness uses after the guard has run, so the test can inspect the
# guard state without starting AstrBot for real.
STARTUP_REACHED_CODE = 7
STATE_MARKER = "GUARD_STATE"

# Replaces asyncio.run so the process stops right after the guard, and reports the
# process pid next to the pid file content the guard produced.
STARTUP_HARNESS = """
import asyncio
import os
import runpy
import sys

_PID_FILE = os.path.join(os.environ["ASTRBOT_ROOT"], "astrbot.pid")


def _stop_before_start(*args, **kwargs):
    try:
        recorded = int(open(_PID_FILE, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        recorded = -1
    print("GUARD_STATE", os.getpid(), recorded)
    raise SystemExit({code})


asyncio.run = _stop_before_start
sys.argv = [{argv}]
runpy.run_path({main_path}, run_name="__main__")
"""


def _run_main(
    astrbot_root: Path, args: tuple[str, ...] = (), stop_at_startup: bool = False
):
    """Run main.py in a subprocess against an isolated AstrBot root.

    Args:
        astrbot_root: Value for the ASTRBOT_ROOT environment variable.
        args: Command-line arguments passed to main.py.
        stop_at_startup: Swap asyncio.run for a sentinel that reports the guard
            state and exits, so AstrBot itself never starts.

    Returns:
        A tuple of the exit code, the combined output, and the guard process pid
        and recorded pid file value as a pair, or None when the guard never ran.
    """
    env = os.environ.copy()
    env["ASTRBOT_ROOT"] = str(astrbot_root)
    env.pop("ASTRBOT_DESKTOP_CLIENT", None)
    env.pop("ASTRBOT_CLI", None)

    if stop_at_startup:
        command = [
            sys.executable,
            "-c",
            STARTUP_HARNESS.format(
                code=STARTUP_REACHED_CODE,
                argv=", ".join(repr(argument) for argument in ["main.py", *args]),
                main_path=repr(str(MAIN_PY)),
            ),
        ]
    else:
        command = [sys.executable, str(MAIN_PY), *args]

    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    output = completed.stdout + completed.stderr

    guard_state: tuple[int, int] | None = None
    for line in output.splitlines():
        if line.startswith(STATE_MARKER):
            _, process_pid, recorded_pid = line.split()
            guard_state = (int(process_pid), int(recorded_pid))
    return completed.returncode, output, guard_state


def test_guard_exits_when_another_instance_holds_the_lock(tmp_path):
    """A second instance fails fast with an actionable message."""
    holder_pid = "424242"
    (tmp_path / "astrbot.pid").write_text(holder_pid, encoding="utf-8")

    holder_lock = FileLock(tmp_path / "astrbot.lock", timeout=0)
    holder_lock.acquire()
    try:
        exit_code, output, _ = _run_main(tmp_path, stop_at_startup=True)
    finally:
        holder_lock.release()

    assert exit_code == 1, output
    assert "Another AstrBot instance is already running" in output
    assert str(tmp_path) in output
    assert holder_pid in output
    assert "astrbot.lock" in output
    assert "ASTRBOT_ROOT" in output
    # The rejected instance must not overwrite the holder's pid file.
    assert (tmp_path / "astrbot.pid").read_text(encoding="utf-8") == holder_pid


def test_guard_reports_unknown_holder_when_pid_file_is_missing(tmp_path):
    """A held lock without a readable pid file still aborts startup."""
    holder_lock = FileLock(tmp_path / "astrbot.lock", timeout=0)
    holder_lock.acquire()
    try:
        exit_code, output, _ = _run_main(tmp_path, stop_at_startup=True)
    finally:
        holder_lock.release()

    assert exit_code == 1, output
    assert "holder pid: unknown" in output


def test_guard_allows_startup_when_lock_is_free(tmp_path):
    """A free lock lets startup continue and records the owning pid."""
    exit_code, output, guard_state = _run_main(tmp_path, stop_at_startup=True)

    assert exit_code == STARTUP_REACHED_CODE, output
    assert "Another AstrBot instance is already running" not in output
    assert guard_state is not None
    process_pid, recorded_pid = guard_state
    assert recorded_pid == process_pid


def test_guard_ignores_stale_lock_file_without_holder(tmp_path):
    """A leftover lock file from a dead process does not block startup."""
    (tmp_path / "astrbot.lock").write_text("stale", encoding="utf-8")
    (tmp_path / "astrbot.pid").write_text("999999", encoding="utf-8")

    exit_code, output, guard_state = _run_main(tmp_path, stop_at_startup=True)

    assert exit_code == STARTUP_REACHED_CODE, output
    assert "Another AstrBot instance is already running" not in output
    assert guard_state is not None
    process_pid, recorded_pid = guard_state
    assert recorded_pid == process_pid
    assert recorded_pid != 999999


@pytest.mark.parametrize("help_flag", ["-h", "--help"])
def test_help_is_not_blocked_by_the_guard(tmp_path, help_flag):
    """Both help flags still work while another instance holds the lock."""
    holder_lock = FileLock(tmp_path / "astrbot.lock", timeout=0)
    holder_lock.acquire()
    try:
        exit_code, output, _ = _run_main(tmp_path, (help_flag,))
    finally:
        holder_lock.release()

    assert exit_code == 0, output
    assert "usage:" in output.lower()
    assert "--webui-dir" in output
    assert "--reset-password" in output
    assert "Another AstrBot instance is already running" not in output
    assert not (tmp_path / "astrbot.pid").exists()
