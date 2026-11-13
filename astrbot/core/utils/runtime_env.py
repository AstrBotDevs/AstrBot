import os
import shutil
import sys


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_packaged_desktop_runtime() -> bool:
    return os.environ.get("ASTRBOT_DESKTOP_CLIENT") == "1"


def resolve_windows_shell() -> str:
    """Select the preferred Windows shell for execution and agent instructions.

    Returns:
        PowerShell 7 when on PATH, otherwise Windows PowerShell 5.1.
    """
    return "pwsh.exe" if shutil.which("pwsh") else "powershell.exe"
