"""Regression tests for the plugin updater's Git clone channel."""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import shutil
import sys
import time
import warnings
from pathlib import Path

import pytest

from astrbot.core.star import updater as plugin_updater


class _FakeProcess:
    """Stand-in for asyncio.subprocess.Process that never spawns anything."""

    def __init__(self, returncode: int = 0, on_communicate=None) -> None:
        self.returncode = returncode
        self.killed = False
        self._on_communicate = on_communicate

    async def communicate(self) -> tuple[bytes, bytes]:
        # Git creates the checkout while it runs, so the stub materialises it here.
        if self._on_communicate is not None:
            self._on_communicate()
        return b"", b""

    def kill(self) -> None:
        self.killed = True


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
            "@echo off\r\n"
            f'"{sys.executable}" "{beater}" "{beat}"\r\n',
            encoding="ascii",
        )
    else:
        shim.write_text(
            "#!/bin/sh\n"
            f'"{sys.executable}" "{beater}" "{beat}"\n',
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
    with pytest.raises(RuntimeError, match="timed out"):
        await plugin_updater._PluginUpdater()._clone_repository(
            "https://example.invalid/owner/repo", tmp_path / "plugin"
        )
    elapsed = time.monotonic() - started

    # The fake git blocks for about 10s. Waiting for it to exit is the bug, so the
    # call has to come back close to the 1s deadline instead.
    assert elapsed < 5.0, f"clone timeout took {elapsed:.1f}s, the deadline is 1s"


@pytest.mark.asyncio
async def test_clone_timeout_reaps_the_process_without_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The killed clone must be reaped in the background and leave no warnings."""
    shim = _write_hanging_git(tmp_path)
    monkeypatch.setattr(plugin_updater.shutil, "which", lambda _name: str(shim))
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        with pytest.raises(RuntimeError, match="timed out"):
            await plugin_updater._PluginUpdater()._clone_repository(
                "https://example.invalid/owner/repo", tmp_path / "plugin"
            )
        # Let the background reaper finish, then collect while still recording so an
        # unclosed transport or an un-reaped child would be caught here.
        for _ in range(50):
            if not plugin_updater._CLONE_REAPERS:
                break
            await asyncio.sleep(0.1)
        gc.collect()

    # Only asyncio's own resource warnings are in scope. Other libraries loaded by
    # the test session (aiosqlite, for one) can emit their own ResourceWarning while
    # gc.collect() runs, and those say nothing about this clone.
    resource_warnings = [
        item
        for item in caught
        if item.category is ResourceWarning
        and "asyncio" in str(item.filename).replace("\\", "/")
    ]
    assert not resource_warnings, [str(item.message) for item in resource_warnings]
    assert not plugin_updater._CLONE_REAPERS, "the reaper task was never released"


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
    with pytest.raises(RuntimeError, match="timed out"):
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
async def test_clone_timeout_survives_a_broken_tree_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing tree kill must degrade to the single-process kill, not raise."""
    if sys.platform == "win32":
        # Make `taskkill` unfindable without disturbing anything else the clone runs.
        real_create_subprocess_exec = asyncio.create_subprocess_exec

        async def flaky_create_subprocess_exec(*args, **kwargs):
            if args and str(args[0]).lower().endswith("taskkill"):
                raise FileNotFoundError("taskkill is unavailable")
            return await real_create_subprocess_exec(*args, **kwargs)

        monkeypatch.setattr(
            plugin_updater.asyncio,
            "create_subprocess_exec",
            flaky_create_subprocess_exec,
        )
    else:

        def unavailable(*_args, **_kwargs):
            raise OSError("tree kill unavailable")

        monkeypatch.setattr(plugin_updater.os, "killpg", unavailable)

    shim = _write_hanging_git(tmp_path)
    monkeypatch.setattr(plugin_updater.shutil, "which", lambda _name: str(shim))
    monkeypatch.setattr(plugin_updater, "PLUGIN_GIT_CLONE_TIMEOUT_SECONDS", 1)

    started = time.monotonic()
    with caplog.at_level(logging.DEBUG, logger="astrbot"):
        with pytest.raises(RuntimeError, match="timed out"):
            await plugin_updater._PluginUpdater()._clone_repository(
                "https://example.invalid/owner/repo", tmp_path / "plugin"
            )
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"the degraded kill path took {elapsed:.1f}s"
    assert "Failed to kill the git clone process tree" in caplog.text
