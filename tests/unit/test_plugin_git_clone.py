"""Regression tests for the plugin updater's Git clone channel."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.repository import GitCloneTimeoutError
from astrbot.core.star import updater as plugin_updater
from astrbot.core.star.star_manager import StarMetadata


class _FakeProcess:
    """Stand-in for asyncio.subprocess.Process that never spawns anything.

    Args:
        communicate_hangs: Whether ``communicate`` blocks until the deadline cancels
            it, like a clone that waits for a credential prompt.
        wait_hangs: Whether ``wait`` never finishes, like a killed clone whose
            inherited pipe handles are still open in a surviving helper.
        on_communicate: Callback invoked before ``communicate`` blocks, used to
            materialise the checkout Git would have created.
    """

    def __init__(
        self,
        *,
        communicate_hangs: bool = False,
        wait_hangs: bool = False,
        on_communicate=None,
    ) -> None:
        self.pid = 4242
        self.returncode: int | None = None
        self.killed = False
        self.waited = False
        self._communicate_hangs = communicate_hangs
        self._wait_hangs = wait_hangs
        self._on_communicate = on_communicate

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._on_communicate is not None:
            self._on_communicate()
        if self._communicate_hangs:
            await asyncio.sleep(3600)
        self.returncode = 0
        return b"", b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.waited = True
        if self._wait_hangs:
            await asyncio.sleep(3600)
        return self.returncode or 0


class _FakeKiller:
    """Stand-in for the ``taskkill`` process used by the Windows tree kill."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    async def wait(self) -> int:
        return self.returncode


def _install_fake_clone(
    monkeypatch: pytest.MonkeyPatch,
    process: _FakeProcess,
    killer: _FakeKiller | None = None,
) -> None:
    """Route the updater's subprocess spawns to the given fakes.

    The fake pid belongs to no process this test owns, so the tree kill must be
    stubbed too: a real group signal or a real ``taskkill`` would aim at an unrelated
    process. A stubbed ``killpg`` covers POSIX and a ``_FakeKiller(returncode=0)``
    covers Windows.

    Args:
        monkeypatch: Test monkeypatch handle.
        process: Fake clone process returned for the ``git`` invocation.
        killer: Fake ``taskkill`` process for the tests that exercise that branch.
    """
    # `killpg` only exists on POSIX; adding it on Windows simply makes the unused
    # attribute available to the monkeypatch undo.
    monkeypatch.setattr(
        plugin_updater.os, "killpg", lambda *_args, **_kwargs: None, raising=False
    )

    async def fake_create_subprocess_exec(*args, **_kwargs):
        if str(args[0]).lower().endswith("taskkill"):
            assert killer is not None, "the test did not expect a taskkill spawn"
            return killer
        return process

    monkeypatch.setattr(
        plugin_updater.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )


def _shim_path(directory: Path) -> Path:
    return directory / ("git.bat" if sys.platform == "win32" else "git")


def _write_hanging_git(directory: Path) -> Path:
    """Create an executable `git` that never answers, like a blocked prompt.

    On POSIX the shim spawns `sleep`, and on Windows the batch file spawns `ping`;
    in both cases the helper process inherits the clone's stdout/stderr handles and
    outlives it, which is exactly the situation that used to keep the pipes open.
    `timeout.exe` cannot be used here because it refuses redirected stdin.
    """
    shim = _shim_path(directory)
    if sys.platform == "win32":
        shim.write_text("@echo off\r\nping -n 11 127.0.0.1 >nul\r\n", encoding="ascii")
    else:
        shim.write_text("#!/bin/sh\nsleep 10\n", encoding="utf-8")
        shim.chmod(0o755)
    return shim


def _write_beating_git(directory: Path) -> tuple[Path, Path]:
    """Create a fake `git` whose grandchild keeps appending to a file.

    The beat file is how the tests observe whether the helper process survived:
    a live grandchild keeps growing it, a killed one stops.
    """
    beat = directory / "beats.txt"
    beater = directory / "beater.py"
    beater.write_text(
        "import sys, time\n"
        "path = sys.argv[1]\n"
        "for _ in range(400):\n"
        "    with open(path, 'a') as handle:\n"
        "        handle.write('x')\n"
        "    time.sleep(0.05)\n",
        encoding="ascii",
    )
    shim = _shim_path(directory)
    if sys.platform == "win32":
        shim.write_text(
            f'@echo off\r\n"{sys.executable}" "{beater}" "{beat}"\r\n',
            encoding="ascii",
        )
    else:
        shim.write_text(
            f'#!/bin/sh\n"{sys.executable}" "{beater}" "{beat}"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
    return shim, beat


@pytest.mark.asyncio
async def test_clone_invokes_git_without_any_interactive_prompt_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No prompt path may survive: not the terminal, a helper, askpass or stdin."""
    captured: dict[str, object] = {}
    target = tmp_path / "plugin"
    fake_process = _FakeProcess(
        on_communicate=lambda: (target / ".git").mkdir(parents=True, exist_ok=True)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return fake_process

    # An IDE shell commonly exports these; they must not reach the clone.
    monkeypatch.setenv("GIT_ASKPASS", "/opt/ide/askpass")
    monkeypatch.setenv("SSH_ASKPASS", "/opt/ide/askpass")
    monkeypatch.setattr(plugin_updater.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        plugin_updater.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    await plugin_updater._PluginUpdater()._clone_repository(
        "https://example.invalid/owner/repo", target
    )

    args = captured["args"]
    kwargs = captured["kwargs"]
    assert isinstance(args, tuple) and isinstance(kwargs, dict)
    # Credential helpers are reset on the command line before the subcommand.
    assert "-c" in args
    assert args[args.index("-c") + 1] == "credential.helper="
    assert args.index("-c") < args.index("clone")
    env = kwargs["env"]
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    # Both askpass hooks are neutralised with a real path that is not a program, and
    # the inherited values are gone; an empty value is interpreted inconsistently by
    # different git versions, so the null device is used instead.
    assert env["GIT_ASKPASS"] == os.devnull
    assert env["SSH_ASKPASS"] == os.devnull
    assert env["GIT_ASKPASS"] != "/opt/ide/askpass"
    assert "BatchMode=yes" in env["GIT_SSH_COMMAND"]
    assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
    # Git metadata must not survive a successful clone.
    assert not (target / ".git").exists()


@pytest.mark.asyncio
async def test_clone_timeout_returns_within_a_hard_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clone that never answers must surface the timeout, not hang past it."""
    shim = _write_hanging_git(tmp_path)
    monkeypatch.setattr(plugin_updater.shutil, "which", lambda _name: str(shim))
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 1)

    started = time.monotonic()
    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", tmp_path / "plugin"
        )
    elapsed = time.monotonic() - started

    # The fake git blocks for about 10s. Waiting for it to exit is the bug, so the
    # call has to come back close to the 1s deadline instead.
    assert elapsed < 5.0, f"clone timeout took {elapsed:.1f}s, the deadline is 1s"


@pytest.mark.asyncio
async def test_clone_timeout_reaps_the_killed_clone_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The killed clone must be reaped by the time the caller sees the timeout."""
    shim = _write_hanging_git(tmp_path)
    monkeypatch.setattr(plugin_updater.shutil, "which", lambda _name: str(shim))
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 1)

    real_create_subprocess_exec = asyncio.create_subprocess_exec
    completed_waits: list[int] = []

    async def capture_create_subprocess_exec(*args, **kwargs):
        process = await real_create_subprocess_exec(*args, **kwargs)
        if str(args[0]) == str(shim):
            # `returncode` alone proves nothing: the child watcher fills it in as soon as
            # the clone exits, even while a helper still holds the pipes, so a `wait()`
            # could never finish. Only a completed wait is recorded here.
            real_wait = process.wait

            async def recorded_wait(*wait_args, **wait_kwargs):
                returncode = await real_wait(*wait_args, **wait_kwargs)
                completed_waits.append(returncode)
                return returncode

            process.wait = recorded_wait
        return process

    monkeypatch.setattr(
        plugin_updater.asyncio,
        "create_subprocess_exec",
        capture_create_subprocess_exec,
    )

    pending_before = asyncio.all_tasks()
    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", tmp_path / "plugin"
        )

    assert len(completed_waits) == 1, (
        "the killed clone was not waited for before the timeout surfaced"
    )
    # A fire-and-forget reaper would keep the subprocess transport alive past the
    # deadline, and would still be pending here.
    leftover = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and task not in pending_before
    ]
    assert not leftover, [task.get_coro() for task in leftover]


@pytest.mark.asyncio
async def test_clone_timeout_kills_the_helper_process_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper a clone spawned must die with it instead of lingering."""
    if sys.platform == "win32" and shutil.which("taskkill") is None:
        pytest.skip("taskkill is missing, the Windows tree kill cannot be exercised")

    shim, beat = _write_beating_git(tmp_path)
    monkeypatch.setattr(plugin_updater.shutil, "which", lambda _name: str(shim))
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 1)

    started = time.monotonic()
    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", tmp_path / "plugin"
        )
    elapsed = time.monotonic() - started

    # Two independent properties. The deadline must not wait for the helper - before the
    # fix this call blocked for the full 20s the helper ran, which alone would make the
    # beat file look quiet - and the helper must be gone afterwards, because killing the
    # clone process alone left it running.
    assert elapsed < 5.0, f"the timeout path waited {elapsed:.1f}s for the helper"
    await asyncio.sleep(1.0)
    first_size = beat.stat().st_size if beat.exists() else 0
    assert first_size > 0, "the helper never started, the tree kill cannot be observed"
    await asyncio.sleep(1.5)
    second_size = beat.stat().st_size if beat.exists() else 0
    assert second_size == first_size, (
        f"the helper process survived the tree kill (+{second_size - first_size} bytes)"
    )


@pytest.mark.asyncio
async def test_clone_timeout_removes_the_checkout_after_the_clone_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The partial checkout may only be removed once the clone is confirmed stopped."""
    target = tmp_path / "plugin"
    process = _FakeProcess(
        communicate_hangs=True,
        on_communicate=lambda: target.mkdir(parents=True, exist_ok=True),
    )
    # The tree kill itself is covered by the tests above; this one only observes the
    # order of the wait and the removal.
    _install_fake_clone(monkeypatch, process, _FakeKiller(returncode=0))
    observed: list[bool] = []
    monkeypatch.setattr(
        plugin_updater, "remove_dir", lambda _path: observed.append(process.waited)
    )
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_KILL_TIMEOUT_SECONDS", 1)

    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", target
        )

    assert not process.killed, "the tree kill degraded instead of succeeding"
    assert observed == [True], (
        "the checkout was removed without waiting for the clone to stop"
    )


@pytest.mark.asyncio
async def test_clone_timeout_cleanup_failure_keeps_the_timeout_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing checkout cleanup must not replace the timeout the caller needs."""
    target = tmp_path / "plugin"
    process = _FakeProcess(
        communicate_hangs=True,
        on_communicate=lambda: target.mkdir(parents=True, exist_ok=True),
    )
    _install_fake_clone(monkeypatch, process, _FakeKiller(returncode=0))

    def failing_remove_dir(_path):
        raise PermissionError("the checkout is still held open")

    monkeypatch.setattr(plugin_updater, "remove_dir", failing_remove_dir)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_KILL_TIMEOUT_SECONDS", 1)

    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", target
        )

    assert not process.killed, "the tree kill degraded instead of succeeding"


@pytest.mark.asyncio
async def test_clone_timeout_falls_back_when_taskkill_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A taskkill that gives up on the tree must not end the kill attempt."""
    target = tmp_path / "plugin"
    process = _FakeProcess(
        communicate_hangs=True,
        on_communicate=lambda: target.mkdir(parents=True, exist_ok=True),
    )
    # Only the updater module is switched to Windows: the process tree kill has to
    # take that branch everywhere, and no real taskkill is spawned here.
    monkeypatch.setattr(plugin_updater, "sys", SimpleNamespace(platform="win32"))
    _install_fake_clone(monkeypatch, process, _FakeKiller(returncode=1))
    monkeypatch.setattr(plugin_updater, "remove_dir", lambda _path: True)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_KILL_TIMEOUT_SECONDS", 1)

    with caplog.at_level(logging.DEBUG, logger="astrbot"):
        with pytest.raises(GitCloneTimeoutError, match="timed out"):
            await plugin_updater._PluginUpdater()._clone_repository(
                "https://example.invalid/owner/repo", target
            )

    assert process.killed, "a taskkill exit code was treated as a successful kill"
    assert "Failed to kill the git clone process tree" in caplog.text


@pytest.mark.asyncio
async def test_clone_timeout_keeps_the_tree_kill_when_taskkill_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful taskkill is trusted, so no second kill is attempted."""
    target = tmp_path / "plugin"
    process = _FakeProcess(
        communicate_hangs=True,
        on_communicate=lambda: target.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(plugin_updater, "sys", SimpleNamespace(platform="win32"))
    _install_fake_clone(monkeypatch, process, _FakeKiller(returncode=0))
    monkeypatch.setattr(plugin_updater, "remove_dir", lambda _path: True)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_KILL_TIMEOUT_SECONDS", 1)

    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", target
        )

    assert not process.killed


@pytest.mark.asyncio
async def test_clone_timeout_leaves_no_reaper_when_the_kill_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A clone stuck past the kill must not keep a background task alive forever."""
    target = tmp_path / "plugin"
    process = _FakeProcess(
        communicate_hangs=True,
        wait_hangs=True,
        on_communicate=lambda: target.mkdir(parents=True, exist_ok=True),
    )
    _install_fake_clone(monkeypatch, process)

    if sys.platform == "win32":

        async def unavailable_taskkill(*args, **kwargs):
            if str(args[0]).lower().endswith("taskkill"):
                raise FileNotFoundError("taskkill is unavailable")
            return process

        monkeypatch.setattr(
            plugin_updater.asyncio, "create_subprocess_exec", unavailable_taskkill
        )
    else:

        def unavailable(*_args, **_kwargs):
            raise OSError("tree kill unavailable")

        monkeypatch.setattr(plugin_updater.os, "killpg", unavailable)

    monkeypatch.setattr(plugin_updater, "remove_dir", lambda _path: True)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_KILL_TIMEOUT_SECONDS", 0.2)

    pending_before = asyncio.all_tasks()
    started = time.monotonic()
    with caplog.at_level(logging.DEBUG, logger="astrbot"):
        with pytest.raises(GitCloneTimeoutError, match="timed out"):
            await plugin_updater._PluginUpdater()._clone_repository(
                "https://example.invalid/owner/repo", target
            )
    elapsed = time.monotonic() - started

    assert process.killed
    assert "Failed to kill the git clone process tree" in caplog.text
    assert elapsed < 5.0, f"the degraded kill path took {elapsed:.1f}s"
    leftover = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and task not in pending_before
    ]
    assert not leftover, [task.get_coro() for task in leftover]


@pytest.mark.asyncio
async def test_repository_inspection_keeps_the_timeout_when_teardown_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkout that cannot be torn down must not report a filesystem error."""
    updater = plugin_updater._PluginUpdater()
    open_handles: list = []

    async def failing_clone(_repo_url, target_path):
        checkout = Path(target_path)
        checkout.mkdir(parents=True)
        open_handles.append((checkout / "held.txt").open("w", encoding="utf-8"))
        if sys.platform != "win32":
            # Unlinking an open file succeeds on POSIX, so make the directory itself
            # refuse the removal that a surviving helper causes on Windows.
            checkout.chmod(0o500)
        raise GitCloneTimeoutError("Git clone timed out after 180s.")

    monkeypatch.setattr(updater, "_clone_repository", failing_clone)
    monkeypatch.setattr(plugin_updater, "get_astrbot_temp_path", lambda: str(tmp_path))

    try:
        with pytest.raises(GitCloneTimeoutError, match="timed out"):
            await updater.inspect_repository("git@github.com:AstrBotDevs/demo.git")
    finally:
        for handle in open_handles:
            handle.close()
        if sys.platform != "win32":
            for path in tmp_path.rglob("*"):
                if path.is_dir():
                    path.chmod(0o700)


@pytest.mark.asyncio
async def test_install_keeps_the_timeout_when_the_staging_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staging cleanup error must not replace the timeout the caller needs."""
    updater = plugin_updater._PluginUpdater()

    async def failing_clone(_repo_url, target_path):
        Path(target_path).mkdir(parents=True)
        raise GitCloneTimeoutError("Git clone timed out after 180s.")

    def failing_remove_dir(_path):
        raise PermissionError("the staging directory is still held open")

    monkeypatch.setattr(updater, "_clone_repository", failing_clone)
    monkeypatch.setattr(plugin_updater, "remove_dir", failing_remove_dir)

    with pytest.raises(GitCloneTimeoutError, match="timed out"):
        await updater.install(
            "git@github.com:AstrBotDevs/demo.git", target_dir=tmp_path / "plugin"
        )


@pytest.mark.asyncio
async def test_update_keeps_the_timeout_when_the_staging_teardown_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staging teardown error must not replace the timeout the caller needs."""
    if sys.platform != "win32":
        # Outside Windows an open file does not block deletion, so the staging teardown
        # cannot be made to fail with a real checkout on disk.
        pytest.skip("only Windows keeps a deleted file locked")
    updater = plugin_updater._PluginUpdater()
    monkeypatch.setattr(updater, "plugin_store_path", str(tmp_path))
    open_handles: list = []

    async def failing_clone(_repo_url, target_path):
        checkout = Path(target_path)
        checkout.mkdir(parents=True)
        open_handles.append((checkout / "held.txt").open("w", encoding="utf-8"))
        raise GitCloneTimeoutError("Git clone timed out after 180s.")

    monkeypatch.setattr(updater, "_clone_repository", failing_clone)
    plugin = StarMetadata(
        name="demo",
        root_dir_name="demo",
        repo="git@github.com:AstrBotDevs/demo.git",
    )

    try:
        with pytest.raises(GitCloneTimeoutError, match="timed out"):
            await updater.update(plugin)
    finally:
        for handle in open_handles:
            handle.close()

