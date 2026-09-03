from __future__ import annotations

import sys

from .base import ProcessSandbox, SandboxProcess, SandboxSpec
from .bubblewrap import BubblewrapProcessSandbox
from .seatbelt import SeatbeltProcessSandbox


def create_process_sandbox() -> ProcessSandbox:
    """Select the restricted-process launcher for the current system.

    Returns:
        Bubblewrap on Linux or Seatbelt on macOS.

    Raises:
        RuntimeError: If the current system has no Local sandbox implementation.
    """
    if sys.platform.startswith("linux"):
        return BubblewrapProcessSandbox()
    if sys.platform == "darwin":
        return SeatbeltProcessSandbox()
    raise RuntimeError(
        "The Local execution sandbox is only available on Linux and macOS."
    )


__all__ = (
    "ProcessSandbox",
    "SandboxProcess",
    "SandboxSpec",
    "create_process_sandbox",
)
