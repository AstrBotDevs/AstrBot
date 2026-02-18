from __future__ import annotations

import ctypes
import os
import runpy
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR / "app"
_WINDOWS_DLL_DIRECTORY_HANDLES: list[object] = []


def configure_windows_dll_search_path() -> None:
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    runtime_executable_dir = Path(sys.executable).resolve().parent
    site_packages_dirs = [
        runtime_executable_dir / "Lib" / "site-packages",
        BACKEND_DIR / "python" / "Lib" / "site-packages",
    ]
    candidates = [
        runtime_executable_dir,
        runtime_executable_dir / "DLLs",
        BACKEND_DIR / "python",
        BACKEND_DIR / "python" / "DLLs",
    ]
    for site_packages_dir in site_packages_dirs:
        candidates.extend(
            [
                site_packages_dir / "cryptography.libs",
                site_packages_dir / "cryptography" / "hazmat" / "bindings",
            ],
        )

    normalized_added: set[str] = set()
    path_entries: list[str] = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        candidate_str = str(candidate)
        candidate_key = candidate_str.lower()
        if candidate_key in normalized_added:
            continue
        normalized_added.add(candidate_key)
        path_entries.append(candidate_str)
        try:
            _WINDOWS_DLL_DIRECTORY_HANDLES.append(
                os.add_dll_directory(candidate_str),
            )
        except OSError:
            continue

    if path_entries:
        existing_path = os.environ.get("PATH", "")
        os.environ["PATH"] = (
            ";".join(path_entries + [existing_path])
            if existing_path
            else ";".join(path_entries)
        )


def preload_windows_runtime_dlls() -> None:
    if sys.platform != "win32":
        return

    runtime_executable_dir = Path(sys.executable).resolve().parent
    runtime_dll_dir = runtime_executable_dir / "DLLs"
    backend_runtime_dir = BACKEND_DIR / "python"
    backend_runtime_dll_dir = backend_runtime_dir / "DLLs"
    candidate_dirs = [
        runtime_executable_dir,
        runtime_dll_dir,
        backend_runtime_dir,
        backend_runtime_dll_dir,
    ]
    patterns = [
        "python3.dll",
        "python*.dll",
        "vcruntime*.dll",
        "libcrypto-*.dll",
        "libssl-*.dll",
    ]
    loaded: set[str] = set()
    for candidate_dir in candidate_dirs:
        if not candidate_dir.is_dir():
            continue
        for pattern in patterns:
            for dll_path in candidate_dir.glob(pattern):
                normalized_path = str(dll_path.resolve()).lower()
                if normalized_path in loaded:
                    continue
                loaded.add(normalized_path)
                try:
                    ctypes.WinDLL(str(dll_path))
                except OSError:
                    continue


configure_windows_dll_search_path()
preload_windows_runtime_dlls()

sys.path.insert(0, str(APP_DIR))

main_file = APP_DIR / "main.py"
if not main_file.is_file():
    raise FileNotFoundError(f"Backend entrypoint not found: {main_file}")

sys.argv[0] = str(main_file)
runpy.run_path(str(main_file), run_name="__main__")
