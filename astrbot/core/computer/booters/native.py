"""Native Windows sandbox booter (no third-party software, no admin needed).

Runs agent-generated code under a restricted token of the current user:

- file writes are confined to a per-session work directory via a synthetic
  SID double gate (``CreateRestrictedToken`` + ACL: writes must be allowed
  to the real user AND to the synthetic SID);
- the child runs on a private desktop, isolated from the user's session;
- a Job Object guarantees the whole process tree dies on timeout/shutdown;
- internet access is downgraded to advisory interception (environment
  poisoning) — see the SECURITY note in :class:`NativeSandbox`.

Reads of the host stay available where the DACL grants one of the restricted
SIDs (system directories), which is what the interpreter needs; user-profile
paths are effectively read-denied.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import shutil
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

import pywintypes
import win32con
import win32event
import win32file
import win32job
import win32pipe
import win32process
import win32security

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import (
    get_astrbot_site_packages_path,
    get_astrbot_temp_path,
)

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .local import LocalFileSystemComponent

# Synthetic SID under the NT authority in a range that maps to no real
# principal; it only needs to match byte-for-byte between the restricted-SID
# list and the work-directory DACL.
SYNTHETIC_SID = "S-1-5-900000001"
# Groups whose ACEs appear in default system DACLs; required so the child
# can read the interpreter/system files at all.
RESTRICTED_GROUP_SIDS = (
    "S-1-1-0",  # Everyone
    "S-1-5-32-545",  # BUILTIN\Users
    "S-1-5-4",  # INTERACTIVE
    "S-1-5-6",  # SERVICE
    "S-1-5-11",  # Authenticated Users
)
# FILE_GENERIC_READ does not include FILE_EXECUTE; process images need it.
FILE_READ_EXECUTE = 0x1200A9
FILE_MODIFY = 0x1301BF
GENERIC_ALL = 0x10000000
DESKTOP_NAME = "astrbot_native_desktop"


def _synthetic_sid():
    return win32security.ConvertStringSidToSid(SYNTHETIC_SID)


def grant_path_acl(path: Path, sid_text: str, access_mask: int) -> None:
    """Append an inheritable allow-ACE for ``sid_text`` on ``path``."""
    sid = win32security.ConvertStringSidToSid(sid_text)
    sd = win32security.GetNamedSecurityInfo(
        str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
    )
    dacl = sd.GetSecurityDescriptorDacl() or win32security.ACL()
    dacl.AddAccessAllowedAceEx(
        win32security.ACL_REVISION_DS,
        win32security.OBJECT_INHERIT_ACE | win32security.CONTAINER_INHERIT_ACE,
        access_mask,
        sid,
    )
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
        None,
        None,
        dacl,
        None,
    )


def revoke_path_acl(path: Path, sid_text: str) -> None:
    """Remove every ACE for ``sid_text`` from ``path`` (best effort)."""
    sd = win32security.GetNamedSecurityInfo(
        str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
    )
    dacl = sd.GetSecurityDescriptorDacl()
    if dacl is None:
        return
    clean = win32security.ACL()
    for index in range(dacl.GetAceCount()):
        (ace_type, ace_flags), access_mask, ace_sid = dacl.GetAce(index)
        if win32security.ConvertSidToStringSid(ace_sid) == sid_text:
            continue
        if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE:
            clean.AddAccessAllowedAceEx(
                win32security.ACL_REVISION_DS, ace_flags, access_mask, ace_sid
            )
        elif ace_type == win32security.ACCESS_DENIED_ACE_TYPE:
            clean.AddAccessDeniedAceEx(
                win32security.ACL_REVISION_DS, ace_flags, access_mask, ace_sid
            )
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
        None,
        None,
        clean,
        None,
    )


class NativeSandbox:
    """One sandboxed execution context: desktop + restricted token + grants."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = Path(workdir)
        self.desktop_name = f"astrbot_native_{uuid.uuid4().hex[:8]}"
        self._job = None
        self._hdesk = None
        self._prepared = False

    def prepare(self) -> None:
        """Create the isolated desktop, the restricted token, and ACLs."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        synth_text = win32security.ConvertSidToStringSid(_synthetic_sid())
        grant_path_acl(self.workdir, synth_text, FILE_MODIFY)
        # The child interpreter must at least execute; writes stay denied.
        for tree in {Path(sys.base_prefix), Path(sys.exec_prefix)}:
            grant_path_acl(tree, synth_text, FILE_READ_EXECUTE)

        self._hdesk = self._create_desktop()
        self._token = self._make_restricted_token(synth_text)
        self._prepared = True

    def _create_desktop(self) -> int:
        """Create a private desktop granting every restricted SID access.

        A restricted process fails at DLL init (0xC0000142) when the
        desktop DACL has no ACE for one of its restricted SIDs.
        """
        user_sid = win32security.GetTokenInformation(
            win32security.OpenProcessToken(
                win32process.GetCurrentProcess(), win32security.TOKEN_QUERY
            ),
            win32security.TokenUser,
        )
        user_sid_text = win32security.ConvertSidToStringSid(user_sid[0])
        synth_text = win32security.ConvertSidToStringSid(_synthetic_sid())
        grants = "".join(f"(A;;GA;;;{s})" for s in RESTRICTED_GROUP_SIDS)
        sddl = (
            f"D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;{user_sid_text})"
            f"(A;;GA;;;{synth_text}){grants}"
        )
        advapi32 = ctypes.WinDLL("advapi32")
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.ULONG),
        ]
        psd = ctypes.c_void_p()
        size = wintypes.ULONG()
        rc = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(psd), ctypes.byref(size)
        )
        if rc == 0 or not psd.value:
            raise OSError("SDDL -> SD conversion failed")

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [
                ("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL),
            ]

        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(sa)
        sa.lpSecurityDescriptor = psd.value
        sa.bInheritHandle = False
        user32 = ctypes.WinDLL("user32")
        user32.CreateDesktopW.restype = wintypes.HANDLE
        user32.CreateDesktopW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        hdesk = user32.CreateDesktopW(
            self.desktop_name.rsplit("\\", 1)[-1],
            None,
            None,
            0,
            GENERIC_ALL,
            ctypes.byref(sa),
        )
        if not hdesk:
            raise OSError(f"CreateDesktopW failed: {ctypes.GetLastError()}")
        return hdesk

    def _make_restricted_token(self, synth_text: str):
        """Restricted token of the current user: [groups..., synthetic]."""
        sids = [
            (win32security.ConvertStringSidToSid(s), 0) for s in RESTRICTED_GROUP_SIDS
        ]
        sids.append((_synthetic_sid(), 0))
        token = win32security.OpenProcessToken(
            win32process.GetCurrentProcess(),
            win32security.TOKEN_DUPLICATE
            | win32security.TOKEN_QUERY
            | win32security.TOKEN_ASSIGN_PRIMARY,
        )
        return win32security.CreateRestrictedToken(token, 0, [], [], sids)

    def run(self, args: list[str], *, env: dict | None = None, timeout: float = 120):
        """Run ``args`` in the sandbox; return (combined stdout, exit code).

        The child runs on the private desktop with inherited pipes (output
        capture needs no redirects here, unlike a driver-based sandbox), and
        inside a Job Object so timeouts kill the entire tree.
        """
        if not self._prepared:
            raise RuntimeError("sandbox is not prepared")
        child_env = {
            **{k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")},
            # Advisory-only network denial (elevation + WFP would make this
            # kernel-enforced; without them this is best-effort).
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "GIT_SSH_COMMAND": "exit 1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": get_astrbot_site_packages_path(),
        }
        if env:
            child_env.update({str(k): str(v) for k, v in env.items()})

        sa = pywintypes.SECURITY_ATTRIBUTES()
        sa.bInheritHandle = True
        outr, outw = win32pipe.CreatePipe(sa, 0)
        si = win32process.STARTUPINFO()
        si.hStdInput = win32file.CreateFile(
            "NUL",
            win32con.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            sa,
            win32con.OPEN_EXISTING,
            0,
            None,
        )
        si.hStdOutput = outw
        si.hStdError = outw
        si.dwFlags = win32con.STARTF_USESTDHANDLES
        si.lpDesktop = self.desktop_name
        proc = win32process.CreateProcessAsUser(
            self._token,
            None,
            subprocess.list2cmdline(args),
            sa,
            sa,
            True,
            0x00000008,  # DETACHED_PROCESS: no console needed headless
            child_env,
            str(self.workdir),
            si,
        )
        job = win32job.CreateJobObject(None, "")
        limits = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        limits["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, limits
        )
        win32job.AssignProcessToJobObject(job, proc[0])
        self._job = job

        timed_out = False
        wait = win32event.WaitForSingleObject(proc[0], int((timeout or 120) * 1000))
        if wait == win32con.WAIT_TIMEOUT:
            timed_out = True
            win32job.TerminateJobObject(job, 1)
        outw.Close()
        chunks = []
        while True:
            try:
                _hr, data = win32file.ReadFile(outr, 65536)
            except pywintypes.error:
                break
            if not data:
                break
            chunks.append(data.decode("utf-8", errors="replace"))
        outr.Close()
        text = "".join(chunks)
        rc = win32process.GetExitCodeProcess(proc[0])
        proc[0].Close()
        proc[1].Close()
        job.Close()
        self._job = None
        if timed_out:
            raise subprocess.TimeoutExpired(args, timeout or 120, text)
        return text, rc

    def terminate(self) -> None:
        """Kill every process in the sandbox job (no-op if none)."""
        if self._job is not None:
            win32job.TerminateJobObject(self._job, 1)

    def close(self) -> None:
        """Release the desktop handle; ACLs on the workdir go with it."""
        if self._hdesk:
            ctypes.WinDLL("user32").CloseDesktop(self._hdesk)
            self._hdesk = None
        self._prepared = False


class NativeShellComponent(ShellComponent):
    """Shell operations routed through the native sandbox.

    Commands run with cmd.exe inside the sandbox: PowerShell's .NET
    initialization fails under a restricted token (0xC0000142), while cmd
    is self-contained.
    """

    def __init__(self, sandbox: NativeSandbox) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        """Execute a shell command inside the sandbox."""
        if background:
            raise NotImplementedError(
                "Background shell is not supported by the native booter."
            )
        args = ["cmd", "/d", "/s", "/c", command]
        out, rc = await asyncio.to_thread(
            self._sandbox.run, args, env=env, timeout=timeout
        )
        return {"stdout": out, "stderr": "", "exit_code": rc}

    async def exec_managed(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Managed interactive sessions are not supported yet."""
        raise NotImplementedError(
            "Managed shell sessions are not supported by the native booter."
        )


class NativePythonComponent(PythonComponent):
    """Python execution routed through the native sandbox."""

    def __init__(self, sandbox: NativeSandbox) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Execute Python code via a generated script file."""
        script = self._sandbox.workdir / f".astrbot_py_{uuid.uuid4().hex}.py"
        script.write_text(code, encoding="utf-8")
        base_exe = Path(sys.base_prefix) / "python.exe"
        try:
            out, rc = await asyncio.to_thread(
                self._sandbox.run, [str(base_exe), str(script)], timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return {
                "data": {
                    "output": {"text": "", "images": []},
                    "error": "Execution timed out.",
                }
            }
        finally:
            script.unlink(missing_ok=True)
        text = "" if silent else out
        error = "" if rc == 0 else out
        return {"data": {"output": {"text": text, "images": []}, "error": error}}


class NativeFileSystemComponent(FileSystemComponent):
    """File operations confined to the sandbox work directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()
        self._inner = LocalFileSystemComponent()

    def _resolve(self, path: str) -> str:
        """Resolve ``path`` inside the root; raise if it escapes."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._root / candidate
        resolved = candidate.resolve()
        if self._root not in resolved.parents and resolved != self._root:
            raise PermissionError(f"Path escapes the sandbox work directory: {path}")
        return str(resolved)

    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict:
        return await self._inner.create_file(self._resolve(path), content, mode)

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict:
        return await self._inner.read_file(self._resolve(path), encoding, offset, limit)

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict:
        return await self._inner.search_files(
            pattern,
            self._resolve(path) if path else str(self._root),
            glob,
            after_context,
            before_context,
        )

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> dict:
        return await self._inner.edit_file(
            self._resolve(path), old_string, new_string, replace_all, encoding
        )

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict:
        return await self._inner.write_file(
            self._resolve(path), content, mode, encoding
        )

    async def delete_file(self, path: str) -> dict:
        return await self._inner.delete_file(self._resolve(path))

    async def list_dir(self, path: str = ".", show_hidden: bool = False) -> dict:
        return await self._inner.list_dir(self._resolve(path), show_hidden)


class NativeBooter(ComputerBooter):
    """Computer booter that sandboxes agent code with native Windows APIs."""

    def __init__(self, sandbox_cfg: dict | None = None) -> None:
        self._session_id: str | None = None
        self._sandbox: NativeSandbox | None = None
        self._fs = NativeFileSystemComponent(Path(get_astrbot_temp_path()))
        self._python: NativePythonComponent | None = None
        self._shell: NativeShellComponent | None = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("python", "shell", "filesystem")

    @property
    def fs(self) -> FileSystemComponent:
        return self._fs

    @property
    def python(self) -> PythonComponent:
        if self._python is None:
            raise RuntimeError("Native booter is not booted.")
        return self._python

    @property
    def shell(self) -> ShellComponent:
        if self._shell is None:
            raise RuntimeError("Native booter is not booted.")
        return self._shell

    async def boot(self, session_id: str) -> None:
        """Prepare the desktop, token, and work directory for this session."""

        def _boot() -> None:
            key = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex[:12]
            workdir = Path(get_astrbot_temp_path()) / "native" / key / "work"
            sandbox = NativeSandbox(workdir)
            sandbox.prepare()
            self._sandbox = sandbox
            self._fs = NativeFileSystemComponent(workdir)
            self._python = NativePythonComponent(sandbox)
            self._shell = NativeShellComponent(sandbox)
            self._session_id = session_id
            logger.info(
                "[Computer] Native sandbox ready: session=%s, workdir=%s",
                session_id,
                workdir,
            )

        await asyncio.to_thread(_boot)

    async def shutdown(self, **kwargs) -> None:
        """Kill the sandbox job, close the desktop, and revoke ACL grants."""

        def _shutdown() -> None:
            sandbox = self._sandbox
            self._sandbox = None
            self._python = None
            self._shell = None
            if sandbox is None:
                return
            sandbox.terminate()
            synth_text = win32security.ConvertSidToStringSid(_synthetic_sid())
            for tree in {Path(sys.base_prefix), Path(sys.exec_prefix)}:
                try:
                    revoke_path_acl(tree, synth_text)
                except Exception as exc:
                    logger.warning(
                        "[Computer] Failed to revoke ACL on %s: %s", tree, exc
                    )
            try:
                shutil.rmtree(sandbox.workdir, ignore_errors=True)
            except Exception as exc:
                logger.warning(
                    "[Computer] Failed to remove workdir %s: %s", sandbox.workdir, exc
                )
            sandbox.close()

        await asyncio.to_thread(_shutdown)

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Copy a host file into the sandbox work directory."""
        sandbox = self._require_sandbox()
        dest = (sandbox.workdir / file_name.lstrip("/\\")).resolve()
        dest.relative_to(sandbox.workdir.resolve())
        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(lambda: shutil.copyfile(path, dest))
        return {"success": True, "file_path": str(dest)}

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Copy a file from the sandbox work directory to a host path."""
        sandbox = self._require_sandbox()
        source = (sandbox.workdir / remote_path.lstrip("/\\")).resolve()
        source.relative_to(sandbox.workdir.resolve())
        await asyncio.to_thread(lambda: shutil.copyfile(source, local_path))

    async def available(self) -> bool:
        """Check that the sandbox is still prepared."""
        return self._sandbox is not None and self._sandbox._prepared

    def _require_sandbox(self) -> NativeSandbox:
        if self._sandbox is None:
            raise RuntimeError("Native booter is not booted.")
        return self._sandbox
