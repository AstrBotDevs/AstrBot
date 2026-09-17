"""Process-level restart support for the AstrBot lifecycle."""

import os
import subprocess
import sys
import time

import psutil

from astrbot.core import logger
from astrbot.core.desktop_runtime import (
    DESKTOP_MANAGED_RESTART_MESSAGE,
    is_desktop_managed_backend,
)

__all__ = ["restart_process"]


def _terminate_child_processes() -> None:
    """Terminate all child processes owned by the current process."""
    try:
        parent = psutil.Process(os.getpid())
        children = parent.children(recursive=True)
        logger.info("Terminating %s child processes.", len(children))
        for child in children:
            logger.info("Terminating child process %s", child.pid)
            child.terminate()
            try:
                child.wait(timeout=3)
            except psutil.NoSuchProcess:
                continue
            except psutil.TimeoutExpired:
                logger.info(
                    "Child process %s did not terminate cleanly; killing it.",
                    child.pid,
                )
                child.kill()
    except psutil.NoSuchProcess:
        pass


def _collect_flag_values(argv: list[str], flag: str) -> str | None:
    """Collect a possibly space-separated command-line flag value.

    Args:
        argv: Command-line arguments excluding the executable.
        flag: Option whose value should be collected.

    Returns:
        The collected value, or None when the flag has no value.
    """
    try:
        index = argv.index(flag)
    except ValueError:
        return None

    value_parts: list[str] = []
    for arg in argv[index + 1 :]:
        if arg.startswith("-"):
            break
        if arg:
            value_parts.append(arg)
    return " ".join(value_parts).strip() or None


def _build_frozen_restart_args() -> list[str]:
    """Build the arguments preserved when restarting a frozen application.

    Returns:
        Arguments required to preserve the configured WebUI directory.
    """
    webui_dir = _collect_flag_values(list(sys.argv[1:]), "--webui-dir")
    if not webui_dir:
        webui_dir = os.environ.get("ASTRBOT_WEBUI_DIR")
    return ["--webui-dir", webui_dir] if webui_dir else []


def _reset_pyinstaller_environment() -> None:
    """Prepare PyInstaller environment variables for a clean child process."""
    if not getattr(sys, "frozen", False):
        return
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(os.environ):
        if key.startswith("_PYI_"):
            os.environ.pop(key, None)


def _build_restart_argv(executable: str) -> list[str]:
    """Build the platform-appropriate process argument vector.

    Args:
        executable: Python or frozen application executable.

    Returns:
        Argument vector for the replacement process.
    """
    if os.environ.get("ASTRBOT_CLI") == "1":
        return [executable, "-m", "astrbot.cli.__main__", *sys.argv[1:]]
    if getattr(sys, "frozen", False):
        return [executable, *_build_frozen_restart_args()]
    return [executable, *sys.argv]


def _exec_restart(executable: str, argv: list[str]) -> None:
    """Replace the current process or spawn its Windows replacement.

    Args:
        executable: Python or frozen application executable.
        argv: Argument vector for the replacement process.
    """
    if os.name == "nt" and getattr(sys, "frozen", False):
        quoted_executable = f'"{executable}"' if " " in executable else executable
        quoted_args = [f'"{arg}"' if " " in arg else arg for arg in argv[1:]]
        os.execl(executable, quoted_executable, *quoted_args)
        return
    if os.name == "nt":
        subprocess.Popen(
            [executable, *argv[1:]],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        os._exit(0)
    os.execv(executable, argv)


def restart_process(delay: int = 3) -> None:
    """Restart the current AstrBot process after a short delay.

    Args:
        delay: Seconds to wait before replacing the current process.

    Raises:
        RuntimeError: If an external desktop application owns the process lifecycle.
        OSError: If the replacement process cannot be started.
    """
    if is_desktop_managed_backend():
        logger.error(DESKTOP_MANAGED_RESTART_MESSAGE)
        raise RuntimeError(DESKTOP_MANAGED_RESTART_MESSAGE)

    time.sleep(delay)
    _terminate_child_processes()
    executable = sys.executable
    try:
        _reset_pyinstaller_environment()
        _exec_restart(executable, _build_restart_argv(executable))
    except Exception as exc:
        logger.error(
            "Restart failed (%s, %s). Try restarting manually.", executable, exc
        )
        raise
