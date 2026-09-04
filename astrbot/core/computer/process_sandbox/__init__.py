from __future__ import annotations

import sys

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


__all__ = (
    "ProcessSandbox",
    "SandboxLimits",
    "SandboxProcess",
    "SandboxRunResult",
    "SandboxSpec",
    "SandboxTimeoutError",
    "create_process_sandbox",
)
