from __future__ import annotations

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
    candidates = [
        runtime_executable_dir,
        runtime_executable_dir / "DLLs",
        BACKEND_DIR / "python",
        BACKEND_DIR / "python" / "DLLs",
    ]

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


configure_windows_dll_search_path()

sys.path.insert(0, str(APP_DIR))

main_file = APP_DIR / "main.py"
if not main_file.is_file():
    raise FileNotFoundError(f"Backend entrypoint not found: {main_file}")

sys.argv[0] = str(main_file)
runpy.run_path(str(main_file), run_name="__main__")
