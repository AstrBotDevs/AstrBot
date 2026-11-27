from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

import pytest

from astrbot.core.astr_agent_runtime.computer.process_sandbox import (
    SandboxSpec,
    seatbelt,
)


@pytest.mark.parametrize("executable", [False, True])
def test_seatbelt_grants_nested_search_executable_precise_file_access(
    monkeypatch, tmp_path, executable
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    installation = tmp_path / "homebrew"
    installation.mkdir()
    search_binary = installation / "rg"
    search_binary.touch()
    library = installation / "libpcre2.dylib"
    library.touch()
    unrelated = installation / "private.txt"
    unrelated.touch()
    python = Path(sys.executable).resolve()
    inspected = []

    def read_paths(self, path):
        inspected.append(path)
        return (path, library) if path == search_binary else (path,)

    monkeypatch.setattr(
        seatbelt.shutil, "which", lambda _name, **_kwargs: "/usr/bin/sandbox-exec"
    )
    monkeypatch.setattr(seatbelt.os, "access", lambda path, mode: executable)
    monkeypatch.setattr(
        seatbelt.SeatbeltProcessSandbox, "_executable_read_paths", read_paths
    )
    command = seatbelt.SeatbeltProcessSandbox().build_command(
        [str(python), "-I", "-S", "-c", "pass"],
        SandboxSpec(
            workspace=workspace,
            workspace_writable=False,
            readable_roots=(search_binary,),
        ),
    )
    profile = command[command.index("-p") + 1]
    definition = next(arg for arg in command if arg.startswith("ALLOWED_ROOT_"))
    parameter = definition.split("=", 1)[0]
    assert f'(literal (param "{parameter}"))' in profile
    assert f'(subpath (param "{parameter}"))' not in profile
    assert "(deny file-write*)" in profile
    assert "(deny network*)" in profile
    assert not any(arg.endswith(f"={installation}") for arg in command)
    assert not any(arg.endswith(f"={unrelated}") for arg in command)
    assert (search_binary in inspected) is executable
    assert any(arg.endswith(f"={library}") for arg in command) is executable


@pytest.mark.parametrize("prefix", ["/usr/local", "/opt/homebrew"])
def test_seatbelt_inspects_homebrew_executable_dependencies(monkeypatch, prefix):
    import subprocess

    class ExistingPosixPath(PurePosixPath):
        def resolve(self):
            return self

        def exists(self):
            return True

    executable = ExistingPosixPath(prefix) / "bin" / "rg"
    library = ExistingPosixPath(prefix) / "lib" / "libpcre2.dylib"
    inspected = []

    def run(argv, **kwargs):
        inspected.append(argv[-1])
        dependencies = f"{executable}:\n\t{library} (compatibility version 1.0.0)\n"
        return subprocess.CompletedProcess(argv, 0, dependencies.encode(), b"")

    monkeypatch.setattr(seatbelt, "Path", ExistingPosixPath)
    monkeypatch.setattr(seatbelt.subprocess, "run", run)
    paths = seatbelt.SeatbeltProcessSandbox()._executable_read_paths(executable)
    assert executable in paths
    assert library in paths
    assert str(executable) in inspected
    assert str(library) in inspected
