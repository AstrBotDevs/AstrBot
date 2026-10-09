"""Prepare Windows runtime read access once, before accepting tool calls."""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import win32api
import win32event
import win32process
import win32security
from win32com.shell import shell, shellcon

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.runtime_env import resolve_windows_shell

_startup_lock = threading.Lock()
_attempted = False
_ready = False
_error = (
    "Windows sandbox initialization has not run. Restart AstrBot with Local enabled."
)


def shell_path() -> Path:
    """Return the installed PowerShell executable.

    Returns:
        PowerShell 7 when available, otherwise Windows PowerShell.
    """
    return Path(
        shutil.which("pwsh.exe")
        if resolve_windows_shell() == "pwsh.exe"
        else (
            Path(win32api.GetSystemDirectory())
            / "WindowsPowerShell/v1.0/powershell.exe"
        )
    ).resolve()


def runtime_paths() -> tuple[Path, ...]:
    """Collect runtime directories that sandbox processes need to read.

    Returns:
        Existing Python and PowerShell directories, excluding Windows itself.
    """
    windows = Path(win32api.GetWindowsDirectory()).resolve()
    paths = {
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path(sys.executable).resolve().parent,
        shell_path().parent,
    }
    return tuple(
        sorted(p for p in paths if p.is_dir() and not p.is_relative_to(windows))
    )


def require_windows_sandbox_ready() -> None:
    """Fail closed without ever requesting elevation from a tool call.

    Raises:
        RuntimeError: If startup preparation has not succeeded.
    """
    if not _ready:
        raise RuntimeError(_error)


def _prepare_runtime_acl_elevated(paths: list[Path], sid) -> None:
    """Request one elevation to grant read-only access to protected runtimes.

    Args:
        paths: Fixed runtime directories requiring administrator authorization.
        sid: Installation-specific runtime capability SID.

    Raises:
        PermissionError: If the elevated ACL operation fails.
        OSError: If Windows rejects or the user cancels the elevation request.
    """
    # Execute fixed ACL operations through system PowerShell. Never
    # elevate the Python runtime, a workspace script, or agent input.
    sid_text = win32security.ConvertSidToStringSid(sid)
    script = "$ErrorActionPreference='Stop'; try {\n"
    for path in paths:
        literal = str(path).replace("'", "''")
        script += (
            f"$p='{literal}'; "
            "$a=Get-Acl -LiteralPath $p; "
            f"$s=[System.Security.Principal.SecurityIdentifier]::new('{sid_text}'); "
            "$r=[System.Security.AccessControl.FileSystemAccessRule]::new($s,'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow'); "
            "$a.AddAccessRule($r); Set-Acl -LiteralPath $p -AclObject $a;\n"
        )
    script += "exit 0 } catch { exit 1 }"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    logger.info("Requesting one-time Windows sandbox runtime ACL preparation.")
    elevated = shell.ShellExecuteEx(
        fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
        lpVerb="runas",
        lpFile=str(
            Path(win32api.GetSystemDirectory())
            / "WindowsPowerShell/v1.0/powershell.exe"
        ),
        lpParameters=subprocess.list2cmdline(
            [
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ]
        ),
        nShow=0,
    )
    handle = elevated["hProcess"]
    try:
        win32event.WaitForSingleObject(handle, win32event.INFINITE)
        if win32process.GetExitCodeProcess(handle) != 0:
            raise PermissionError("Elevated runtime ACL preparation failed.")
    finally:
        handle.Close()


def initialize_windows_sandbox(*, allow_elevation: bool = True) -> None:
    """Prepare runtime ACLs with at most one elevation request per process.

    Args:
        allow_elevation: Whether startup may show one UAC prompt. Tests and
            noninteractive hosts can disable elevation and inspect the failure.

    Raises:
        RuntimeError: If authorization fails or the user cancels. No tool call
            retries the request; a subsequent startup is required.
    """
    global _attempted, _ready, _error
    from .base import SandboxSpec
    from .windows import (
        _READ,
        AppContainerProcessSandbox,
        runtime_capability,
        set_directory_access,
    )

    with _startup_lock:
        if _attempted:
            require_windows_sandbox_ready()
            return
        _attempted = True
        try:
            sid = runtime_capability()
            missing = []
            for path in runtime_paths():
                dacl = win32security.GetNamedSecurityInfo(
                    str(path),
                    win32security.SE_FILE_OBJECT,
                    win32security.DACL_SECURITY_INFORMATION,
                ).GetSecurityDescriptorDacl()
                # Persistent grants avoid repeated elevation on later starts.
                if dacl is not None and any(
                    ace[0][0] == win32security.ACCESS_ALLOWED_ACE_TYPE
                    and ace[-1] == sid
                    and ace[1] & _READ == _READ
                    and ace[0][1] & 3 == 3
                    for ace in (dacl.GetAce(i) for i in range(dacl.GetAceCount()))
                ):
                    continue
                try:
                    set_directory_access(path, sid, _READ)
                except win32api.error as exc:
                    if exc.winerror != 5:
                        raise
                    missing.append(path)
            if missing:
                if not allow_elevation:
                    raise PermissionError(
                        "Runtime ACL preparation requires administrator access: "
                        + ", ".join(map(str, missing))
                    )
                _prepare_runtime_acl_elevated(missing, sid)
            _ready = True
            temp_root = Path(get_astrbot_temp_path())
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="windows-probe-", dir=temp_root
            ) as directory:
                result = AppContainerProcessSandbox().run(
                    [sys.executable, "-I", "-c", "pass"],
                    SandboxSpec(Path(directory)),
                    timeout=10,
                    output_limit=4096,
                )
                if result.returncode:
                    raise RuntimeError(
                        f"AppContainer launch probe exited with code {result.returncode}: "
                        + result.stderr.decode("utf-8", errors="replace")
                    )
        except Exception as exc:
            _ready = False
            _error = f"Windows sandbox startup preparation failed: {exc}. Restart AstrBot to retry; tool calls never request elevation."
            raise RuntimeError(_error) from exc
