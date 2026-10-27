from __future__ import annotations

import platform
import shutil
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .base import (
    ProcessSandbox,
    SandboxLimits,
    SandboxProcess,
    SandboxRunResult,
    SandboxSpec,
    SandboxTimeoutError,
)


def create_process_sandbox() -> ProcessSandbox:
    """Select the restricted-process launcher for the current system.

    Returns:
        Bubblewrap on Linux or Seatbelt on macOS.

    Raises:
        RuntimeError: If the current system has no Local sandbox implementation.
    """
    if sys.platform.startswith("linux"):
        from .bubblewrap import BubblewrapProcessSandbox

        return BubblewrapProcessSandbox()
    if sys.platform == "darwin":
        from .seatbelt import SeatbeltProcessSandbox

        return SeatbeltProcessSandbox()
    raise RuntimeError("No Local process sandbox backend is available.")


@lru_cache(maxsize=1)
def get_process_sandbox_status() -> dict:
    """Probe Local isolation once per process, including container restrictions.

    Returns:
        Backend, availability status, and optional startup error. Restart AstrBot
        after changing the isolation environment to refresh the cached result.
    """
    system = platform.system().lower()
    sandbox = {"backend": None, "status": "unsupported"}
    if system == "linux":
        sandbox = {
            "backend": "bubblewrap",
            "status": "detected" if shutil.which("bwrap") else "missing",
        }
    elif system == "darwin":
        sandbox = {
            "backend": "seatbelt",
            "status": (
                "detected"
                if shutil.which("sandbox-exec", path="/usr/bin")
                == "/usr/bin/sandbox-exec"
                else "missing"
            ),
        }
    if sandbox["status"] == "detected":
        try:
            temp_root = Path(get_astrbot_temp_path())
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="sandbox-probe-", dir=temp_root
            ) as workspace:
                result = create_process_sandbox().run(
                    ["/bin/sh", "-c", ":"],
                    SandboxSpec(workspace=Path(workspace)),
                    timeout=5,
                    output_limit=1024,
                )
            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.decode("utf-8", errors="replace").strip()
                    or f"Sandbox probe exited with code {result.returncode}."
                )
        except (OSError, RuntimeError, TimeoutError) as exc:
            sandbox.update(
                status="unavailable", error=str(exc)[:1024] or type(exc).__name__
            )
    return sandbox


__all__ = (
    "ProcessSandbox",
    "SandboxLimits",
    "SandboxProcess",
    "SandboxRunResult",
    "SandboxSpec",
    "SandboxTimeoutError",
    "create_process_sandbox",
    "get_process_sandbox_status",
)
