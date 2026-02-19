#!/usr/bin/env python3
"""Resolve and verify python-build-standalone runtime for desktop packaging."""

from __future__ import annotations

import hashlib
import json
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


def _build_request(url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "astrbot-release-workflow",
    }
    github_token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return urllib.request.Request(url, headers=headers)


def _read_json_with_retries(url: str, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = _build_request(url)
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - network-path fallback
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"Failed to fetch release metadata: {url}") from exc
            time.sleep(attempt * 2)

    raise RuntimeError(f"Failed to fetch release metadata: {url}") from last_error


def _resolve_expected_sha256(release: str, asset_name: str) -> str:
    release_api_url = (
        "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/"
        f"{urllib.parse.quote(release)}"
    )
    release_data = _read_json_with_retries(release_api_url)
    assets = release_data.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("Invalid GitHub release metadata: missing assets list.")

    matched_asset = next(
        (
            item
            for item in assets
            if isinstance(item, dict) and item.get("name") == asset_name
        ),
        None,
    )
    if matched_asset is None:
        raise RuntimeError(
            f"Cannot find expected python-build-standalone asset in release {release}: {asset_name}"
        )

    digest = matched_asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise RuntimeError(
            f"Release metadata does not provide sha256 digest for asset: {asset_name}"
        )
    return digest.split(":", 1)[1].lower()


def _calculate_sha256(file_path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    expected_sha256 = _resolve_expected_sha256(release, asset_name)

    target_runtime_root = runner_temp / "astrbot-cpython-runtime"
    download_archive_path = runner_temp / asset_name
    extract_root = runner_temp / "astrbot-cpython-runtime-extract"

    if target_runtime_root.exists():
        shutil.rmtree(target_runtime_root)
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    _download_with_retries(asset_url, download_archive_path)
    actual_sha256 = _calculate_sha256(download_archive_path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "Downloaded runtime archive sha256 mismatch: "
            + f"expected={expected_sha256} actual={actual_sha256}"
        )

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
