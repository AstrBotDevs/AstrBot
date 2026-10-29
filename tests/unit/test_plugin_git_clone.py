"""Regression tests for the plugin updater's Git clone channel."""

from __future__ import annotations

import asyncio
import os
import sys
import time
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


def _write_hanging_git(directory: Path) -> Path:
    """Create an executable `git` that never answers, like a blocked prompt.

    On POSIX the shim spawns `sleep`, and on Windows the batch file spawns `ping`;
    in both cases the helper process inherits the clone's stdout/stderr handles and
    outlives it, which is exactly the situation that used to keep the pipes open.
    `timeout.exe` cannot be used here because it refuses redirected stdin.
    """
    if sys.platform == "win32":
        shim = directory / "git.bat"
        shim.write_text("@echo off\r\nping -n 11 127.0.0.1 >nul\r\n", encoding="ascii")
    else:
        shim = directory / "git"
        shim.write_text("#!/bin/sh\nsleep 10\n", encoding="utf-8")
        shim.chmod(0o755)
    return shim


@pytest.mark.asyncio
async def test_clone_invokes_git_without_any_interactive_prompt_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clone must disable terminal, helper and askpass prompts, and stdin."""
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
