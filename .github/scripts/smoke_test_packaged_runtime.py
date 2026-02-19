#!/usr/bin/env python3
"""Run smoke checks against bundled desktop runtime python."""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys


def _resolve_runtime_python(runtime_root: pathlib.Path) -> pathlib.Path:
    if sys.platform == "win32":
        candidates = [
            runtime_root / "python.exe",
            runtime_root / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            runtime_root / "bin" / "python3",
            runtime_root / "bin" / "python",
        ]

    runtime_python = next(
        (candidate for candidate in candidates if candidate.is_file()), None
    )
    if runtime_python is None:
        raise RuntimeError(
            f"Packaged runtime python executable is missing under {runtime_root}"
        )
    return runtime_python


def _run_command(
    command: list[str], failure_message: str
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            failure_message
            + (
                result.stderr.strip()
                or result.stdout.strip()
                or f"exit={result.returncode}"
            )
        )
    return result


def _check_runtime_dependencies(runtime_python: pathlib.Path) -> None:
    if sys.platform == "darwin":
        deps = _run_command(
            ["otool", "-L", str(runtime_python)],
            "Failed to inspect macOS runtime by otool: ",
        )
        if "/Library/Frameworks/Python.framework/" in deps.stdout:
            raise RuntimeError(
                "Packaged runtime still links to absolute /Library/Frameworks/Python.framework path."
            )
    elif sys.platform.startswith("linux"):
        deps = _run_command(
            ["ldd", str(runtime_python)],
            "Failed to inspect Linux runtime by ldd: ",
        )
        if "not found" in deps.stdout:
            raise RuntimeError(
                "Packaged runtime has unresolved shared libraries:\n" + deps.stdout
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke test packaged desktop runtime python."
    )
    parser.add_argument(
        "runtime_root",
        nargs="?",
        default="desktop/resources/backend/python",
        help="Path to packaged runtime root directory.",
    )
    args = parser.parse_args()

    runtime_root = pathlib.Path(args.runtime_root)
    runtime_python = _resolve_runtime_python(runtime_root)

    _run_command(
        [str(runtime_python), "-V"], "Packaged runtime python smoke test failed: "
    )
    _run_command(
        [str(runtime_python), "-c", "import ssl"],
        "Packaged runtime ssl smoke test failed: ",
    )
    _check_runtime_dependencies(runtime_python)


if __name__ == "__main__":
    main()
