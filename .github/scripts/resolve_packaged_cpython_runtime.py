#!/usr/bin/env python3
"""Resolve and verify python-build-standalone runtime for desktop packaging."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.request


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _download_with_retries(
    url: str, output_path: pathlib.Path, retries: int = 3
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                with output_path.open("wb") as output:
                    shutil.copyfileobj(response, output)
            return
        except Exception as exc:  # pragma: no cover - network-path fallback
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(
                    f"Failed to download python-build-standalone asset: {url}"
                ) from exc
            time.sleep(attempt * 2)

    raise RuntimeError(
        f"Failed to download python-build-standalone asset: {url}"
    ) from last_error


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
            f"Cannot find verification runtime binary under {runtime_root}"
        )
    return runtime_python


def _run_probe(runtime_python: pathlib.Path, args: list[str], label: str) -> None:
    result = subprocess.run(
        [str(runtime_python), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Packaged runtime {label} probe failed: "
            + (
                result.stderr.strip()
                or result.stdout.strip()
                or f"exit={result.returncode}"
            )
        )


def main() -> None:
    runner_temp_dir = os.environ.get("RUNNER_TEMP_DIR") or os.environ.get("RUNNER_TEMP")
    if not runner_temp_dir:
        raise RuntimeError("RUNNER_TEMP_DIR or RUNNER_TEMP must be set.")
    runner_temp = pathlib.Path(runner_temp_dir)

    release = _require_env("PYTHON_BUILD_STANDALONE_RELEASE")
    version = _require_env("PYTHON_BUILD_STANDALONE_VERSION")
    target = _require_env("PYTHON_BUILD_STANDALONE_TARGET")

    asset_name = f"cpython-{version}+{release}-{target}-install_only_stripped.tar.gz"
    asset_url = (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{release}/{urllib.parse.quote(asset_name)}"
    )

    target_runtime_root = runner_temp / "astrbot-cpython-runtime"
    download_archive_path = runner_temp / asset_name
    extract_root = runner_temp / "astrbot-cpython-runtime-extract"

    if target_runtime_root.exists():
        shutil.rmtree(target_runtime_root)
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    _download_with_retries(asset_url, download_archive_path)

    with tarfile.open(download_archive_path, "r:gz") as archive:
        archive.extractall(extract_root)

    source_runtime_root = extract_root / "python"
    if not source_runtime_root.is_dir():
        raise RuntimeError(
            "Invalid python-build-standalone archive layout: missing top-level python/ directory."
        )

    shutil.copytree(
        source_runtime_root,
        target_runtime_root,
        symlinks=sys.platform != "win32",
    )

    runtime_python = _resolve_runtime_python(target_runtime_root)
    _run_probe(runtime_python, ["-V"], "version")
    _run_probe(runtime_python, ["-c", "import ssl"], "ssl")

    print(f"ASTRBOT_DESKTOP_CPYTHON_HOME={target_runtime_root}")
    print(f"ASTRBOT_DESKTOP_CPYTHON_ASSET={asset_name}")


if __name__ == "__main__":
    main()
