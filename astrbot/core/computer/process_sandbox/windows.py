"""Windows AppContainer execution; imported only on Windows."""

from __future__ import annotations

import asyncio
import base64
import ctypes
import hashlib
import msvcrt
import os
import subprocess
import sys
import threading
import uuid
from contextlib import ExitStack, contextmanager
from ctypes import wintypes as wt
from pathlib import Path

import pywintypes
import win32api
import win32event
import win32job
import win32process
import win32security
from win32com.shell import shell, shellcon

from astrbot.api import logger

from .base import ProcessSandbox, SandboxRunResult, SandboxSpec, SandboxTimeoutError

_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_userenv = ctypes.WinDLL("userenv", use_last_error=True)
_base = ctypes.WinDLL("kernelbase", use_last_error=True)
_advapi = ctypes.WinDLL("advapi32")
_advapi.FreeSid.argtypes = [wt.LPVOID]
_ACL_LOCK = threading.RLock()
_READ = 0x1200A9  # FILE_GENERIC_READ | FILE_GENERIC_EXECUTE
_WRITE = 0x1301BF  # Modify, without WRITE_DAC or WRITE_OWNER
_DENY_WRITE = 0xD0156  # Writes, deletion, ACL changes, and ownership changes


class _SidAttributes(ctypes.Structure):
    _fields_ = [("sid", wt.LPVOID), ("attributes", wt.DWORD)]


class _Capabilities(ctypes.Structure):
    _fields_ = [
        ("sid", wt.LPVOID),
        ("capabilities", ctypes.POINTER(_SidAttributes)),
        ("count", wt.DWORD),
        ("reserved", wt.DWORD),
    ]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("reserved", wt.LPWSTR),
        ("desktop", wt.LPWSTR),
        ("title", wt.LPWSTR),
        ("x", wt.DWORD),
        ("y", wt.DWORD),
        ("xsize", wt.DWORD),
        ("ysize", wt.DWORD),
        ("xchars", wt.DWORD),
        ("ychars", wt.DWORD),
        ("fill", wt.DWORD),
        ("flags", wt.DWORD),
        ("show", wt.WORD),
        ("reserved_size", wt.WORD),
        ("reserved_bytes", wt.LPVOID),
        ("stdin", wt.HANDLE),
        ("stdout", wt.HANDLE),
        ("stderr", wt.HANDLE),
        ("attributes", wt.LPVOID),
    ]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", wt.HANDLE),
        ("thread", wt.HANDLE),
        ("pid", wt.DWORD),
        ("tid", wt.DWORD),
    ]


# Explicit signatures are required for 64-bit handles on x64 and ARM64.
_kernel.LocalFree.argtypes = [wt.LPVOID]
_kernel.LocalFree.restype = wt.LPVOID
_kernel.InitializeProcThreadAttributeList.argtypes = [
    wt.LPVOID,
    wt.DWORD,
    wt.DWORD,
    ctypes.POINTER(ctypes.c_size_t),
]
_kernel.UpdateProcThreadAttribute.argtypes = [
    wt.LPVOID,
    wt.DWORD,
    ctypes.c_size_t,
    wt.LPVOID,
    ctypes.c_size_t,
    wt.LPVOID,
    wt.LPVOID,
]
_kernel.DeleteProcThreadAttributeList.argtypes = [wt.LPVOID]
_kernel.CreateProcessW.argtypes = [
    wt.LPCWSTR,
    wt.LPWSTR,
    wt.LPVOID,
    wt.LPVOID,
    wt.BOOL,
    wt.DWORD,
    wt.LPVOID,
    wt.LPCWSTR,
    ctypes.POINTER(_StartupInfo),
    ctypes.POINTER(_ProcessInfo),
]
_userenv.CreateAppContainerProfile.argtypes = [
    wt.LPCWSTR,
    wt.LPCWSTR,
    wt.LPCWSTR,
    wt.LPVOID,
    wt.DWORD,
    ctypes.POINTER(wt.LPVOID),
]
_userenv.CreateAppContainerProfile.restype = ctypes.c_long
_userenv.DeleteAppContainerProfile.argtypes = [wt.LPCWSTR]
_base.DeriveCapabilitySidsFromName.argtypes = [
    wt.LPCWSTR,
    ctypes.POINTER(ctypes.POINTER(wt.LPVOID)),
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(ctypes.POINTER(wt.LPVOID)),
    ctypes.POINTER(wt.DWORD),
]


def runtime_capability():
    """Return the installation-specific read-only runtime capability SID.

    Returns:
        A copied Windows SID; all native allocations are released.
    """
    identity = str(Path(sys.prefix).resolve()).casefold().encode()
    name = "astrbot.runtime." + hashlib.sha256(identity).hexdigest()[:24]
    groups = ctypes.POINTER(wt.LPVOID)()
    capabilities = ctypes.POINTER(wt.LPVOID)()
    group_count, capability_count = wt.DWORD(), wt.DWORD()
    if not _base.DeriveCapabilitySidsFromName(
        name,
        ctypes.byref(groups),
        ctypes.byref(group_count),
        ctypes.byref(capabilities),
        ctypes.byref(capability_count),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # A SID contains an 8-byte header followed by DWORD subauthorities.
        count = ctypes.c_ubyte.from_address(capabilities[0] + 1).value
        return win32security.SID(ctypes.string_at(capabilities[0], 8 + 4 * count))
    finally:
        for array, count in (
            (groups, group_count.value),
            (capabilities, capability_count.value),
        ):
            for index in range(count):
                _kernel.LocalFree(array[index])
            _kernel.LocalFree(array)


def set_directory_access(path: Path, sid, rights: int | None) -> None:
    """Add or remove only this SID's explicit ACEs, preserving other grants.

    Args:
        path: Existing file or directory to authorize.
        sid: AppContainer or runtime capability SID.
        rights: Access mask, or None to remove this SID's explicit grants.
    """
    with _ACL_LOCK:
        descriptor = win32security.GetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        acl = descriptor.GetSecurityDescriptorDacl()
        if acl is None:
            raise PermissionError(f"Sandbox roots must have an explicit DACL: {path}")
        for index in reversed(range(acl.GetAceCount())):
            ace = acl.GetAce(index)
            if ace[-1] == sid and not ace[0][1] & 0x10:  # INHERITED_ACE
                acl.DeleteAce(index)
        if rights is not None:
            # SetEntriesInAcl puts the new grant before inherited ACEs.
            acl.SetEntriesInAcl(
                [
                    {
                        "AccessPermissions": rights,
                        "AccessMode": win32security.DENY_ACCESS
                        if rights == _DENY_WRITE
                        else win32security.GRANT_ACCESS,
                        "Inheritance": 3 if path.is_dir() else 0,
                        "Trustee": {
                            "TrusteeForm": win32security.TRUSTEE_IS_SID,
                            "TrusteeType": win32security.TRUSTEE_IS_UNKNOWN,
                            "Identifier": sid,
                        },
                    }
                ]
            )
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )


@contextmanager
def _appcontainer_access(roots: dict[Path, int], runtimes: tuple[Path, ...]):
    """Own one profile and its temporary filesystem grants through cleanup.

    Args:
        roots: Validated filesystem roots and their access masks.
        runtimes: Runtime directories to protect from workspace writes.

    Yields:
        The execution-specific AppContainer SID.

    Raises:
        OSError: If Windows cannot create the profile.
        RuntimeError: If a filesystem root cannot be authorized.
    """
    profile = "AstrBot.Run." + uuid.uuid4().hex
    native_sid = wt.LPVOID()
    result = _userenv.CreateAppContainerProfile(
        profile,
        "AstrBot sandbox",
        "Temporary restricted tool process",
        None,
        0,
        ctypes.byref(native_sid),
    )
    if result < 0:
        raise OSError(f"CreateAppContainerProfile failed: 0x{result & 0xFFFFFFFF:08x}")
    authorized = []
    try:
        sid_count = ctypes.c_ubyte.from_address(native_sid.value + 1).value
        sid = win32security.SID(ctypes.string_at(native_sid, 8 + 4 * sid_count))
        for root, rights in roots.items():
            try:
                set_directory_access(root, sid, rights)
            except win32api.error as exc:
                raise RuntimeError(
                    f"Cannot authorize sandbox root {root}: {exc}. "
                    "Choose a directory writable by the AstrBot account. "
                    "Tool calls never request elevation."
                ) from exc
            authorized.append(root)
        for protected in runtimes:
            if any(
                protected.is_relative_to(root) and mask == _WRITE
                for root, mask in roots.items()
            ):
                set_directory_access(protected, sid, _DENY_WRITE)
                authorized.append(protected)
        yield sid
    finally:
        for root in reversed(authorized):
            try:
                set_directory_access(root, sid, None)
            except Exception as exc:
                logger.warning(f"Unable to remove sandbox ACL from {root}: {exc}")
        _advapi.FreeSid(native_sid)
        _userenv.DeleteAppContainerProfile(profile)


class _Pipe:
    """Adapt blocking anonymous pipes to the existing async stream protocol."""

    def __init__(self, fd: int, mode: str) -> None:
        self.file = os.fdopen(fd, mode, buffering=0)
        self.pending = bytearray()

    def write(self, data: bytes) -> None:
        self.pending.extend(data)

    async def drain(self) -> None:
        data = bytes(self.pending)
        self.pending.clear()
        while data:
            written = await asyncio.to_thread(self.file.write, data)
            if not written:
                raise BrokenPipeError("Sandbox standard input is closed.")
            data = data[written:]

    async def read(self, n: int = -1) -> bytes:
        return await asyncio.to_thread(self.file.read, n)


class WindowsSandboxProcess:
    """Own the process, job, pipes, and temporary AppContainer authorization."""

    def __init__(self, process, job, pid, stdin, stdout, stderr, resources: ExitStack):
        self.process = process
        self.job = job
        self.pid = pid
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self._resources = resources
        self._returncode = None
        self._closed = False
        self._handle_lock = threading.RLock()

    @property
    def returncode(self) -> int | None:
        """Return the cached exit status, or None while the process runs.

        Returns:
            The Windows exit code once the process handle is signaled.
        """
        with self._handle_lock:
            if (
                self._returncode is None
                and win32event.WaitForSingleObject(self.process, 0) == 0
            ):
                self._returncode = win32process.GetExitCodeProcess(self.process)
            return self._returncode

    async def wait(self) -> int:
        """Wait for the leader and terminate any remaining job descendants.

        Returns:
            The leader's exit code.
        """
        await asyncio.to_thread(
            win32event.WaitForSingleObject, self.process, win32event.INFINITE
        )
        result = self.returncode
        # Detached descendants must not retain the pipes or outlive their leader.
        self.kill()
        return result

    def interrupt(self) -> None:
        """Reject console interrupts for a process launched without a console.

        Raises:
            RuntimeError: Always; use input or terminate instead.
        """
        raise RuntimeError(
            "AppContainer pipe sessions do not support console interrupts. "
            "Send application input or use action=terminate."
        )

    def terminate(self) -> None:
        """Terminate the entire job because pipe sessions have no console."""
        self.kill()

    def kill(self) -> None:
        """Force termination of every process belonging to this job."""
        with self._handle_lock:
            if not self._closed:
                win32job.TerminateJobObject(self.job, 1)

    def close(self) -> None:
        """Release resources after output readers have finished."""
        # Polling, termination, and cleanup can overlap on different threads.
        with self._handle_lock:
            if self._closed:
                return
            self.kill()
            win32event.WaitForSingleObject(self.process, win32event.INFINITE)
            self._returncode = self.returncode
            self._closed = True
            self._resources.close()


class AppContainerProcessSandbox(ProcessSandbox):
    """Launch native Windows tools using AppContainer and a non-breakaway job."""

    def _spawn(
        self,
        argv: list[str],
        spec: SandboxSpec,
        env: dict[str, str] | None = None,
        *,
        merge_output: bool = False,
    ) -> WindowsSandboxProcess:
        """Create an isolated process, granting only the supplied filesystem roots.

        Args:
            argv: Executable and arguments.
            spec: Workspace, network permission, roots, and job limits.
            env: Explicit child environment additions.
            merge_output: Whether stderr shares the stdout pipe.

        Returns:
            An owned Windows process adapter.

        Raises:
            RuntimeError: If the scope or startup preparation is unsupported.
            OSError: If Windows rejects authorization or process creation.
        """
        from .windows_setup import require_windows_sandbox_ready, runtime_paths

        require_windows_sandbox_ready()
        argv, workspace, additions = self._prepare_command(argv, spec, env=env)
        if spec.filesystem_scope != "workspace":
            raise RuntimeError(
                "Windows restricted execution supports workspace scope only."
            )
        runtimes = runtime_paths()
        roots = {p.resolve(): _READ for p in spec.readable_roots if p.exists()}
        roots.update({p.resolve(): _WRITE for p in spec.writable_roots})
        roots[workspace] = _WRITE if spec.workspace_writable else _READ
        for root, rights in roots.items():
            if rights == _WRITE and any(root.is_relative_to(p) for p in runtimes):
                raise RuntimeError(
                    f"Writable sandbox roots cannot be inside a runtime directory: {root}"
                )
        # Launch-only handles close before returning; transfer session resources
        # to the process adapter only after the process is assigned to its job.
        with ExitStack() as resources, ExitStack() as launch:
            sid = resources.enter_context(_appcontainer_access(roots, runtimes))
            job = win32job.CreateJobObject(None, "")
            resources.callback(job.Close)
            limits = win32job.QueryInformationJobObject(
                job, win32job.JobObjectExtendedLimitInformation
            )
            limits["BasicLimitInformation"].update(
                {
                    "LimitFlags": win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                    | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
                    | win32job.JOB_OBJECT_LIMIT_JOB_TIME,
                    "ActiveProcessLimit": spec.limits.processes,
                    "PerJobUserTimeLimit": spec.limits.cpu_seconds * 10_000_000,
                }
            )
            limits["JobMemoryLimit"] = spec.limits.memory_bytes
            win32job.SetInformationJobObject(
                job, win32job.JobObjectExtendedLimitInformation, limits
            )

            pipes, inherited = [], []
            for index in range(2 if merge_output else 3):
                read_fd, write_fd = os.pipe()
                parent_fd, child_fd = (
                    (write_fd, read_fd) if index == 0 else (read_fd, write_fd)
                )
                launch.callback(os.close, child_fd)
                pipe = _Pipe(parent_fd, "wb" if index == 0 else "rb")
                resources.callback(pipe.file.close)
                pipes.append(pipe)
                inherited.append(msvcrt.get_osfhandle(child_fd))
            stdin, stdout = pipes[:2]
            stderr = None if merge_output else pipes[2]
            for handle in inherited:
                os.set_handle_inheritable(handle, True)
            handle_array = (wt.HANDLE * len(inherited))(*inherited)
            sid_buffers = [
                ctypes.create_string_buffer(bytes(sid)),
                ctypes.create_string_buffer(bytes(runtime_capability())),
            ]
            if spec.allow_network:
                # internetClient and privateNetworkClientServer.
                for capability in ("S-1-15-3-1", "S-1-15-3-3"):
                    sid_buffers.append(
                        ctypes.create_string_buffer(
                            bytes(win32security.ConvertStringSidToSid(capability))
                        )
                    )
            caps_array = (_SidAttributes * (len(sid_buffers) - 1))(
                *[
                    _SidAttributes(ctypes.cast(buf, wt.LPVOID), 4)
                    for buf in sid_buffers[1:]
                ]
            )
            caps = _Capabilities(
                ctypes.cast(sid_buffers[0], wt.LPVOID), caps_array, len(caps_array), 0
            )
            size = ctypes.c_size_t()
            _kernel.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            attributes = ctypes.create_string_buffer(size.value)
            if not _kernel.InitializeProcThreadAttributeList(
                attributes, 2, 0, ctypes.byref(size)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            launch.callback(_kernel.DeleteProcThreadAttributeList, attributes)
            for key, value in ((0x20009, caps), (0x20002, handle_array)):
                if not _kernel.UpdateProcThreadAttribute(
                    attributes,
                    0,
                    key,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                    None,
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
            startup = _StartupInfo()
            startup.cb = ctypes.sizeof(startup)
            startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.stdin, startup.stdout = inherited[:2]
            startup.stderr = inherited[1] if merge_output else inherited[2]
            startup.attributes = ctypes.cast(attributes, wt.LPVOID)
            child_env = dict(additions)
            child_env.update(
                {
                    "SystemRoot": str(Path(win32api.GetWindowsDirectory())),
                    "WINDIR": str(Path(win32api.GetWindowsDirectory())),
                    # Windows uses this to locate the AppContainer profile while
                    # creating the process; omitting it causes WinError 203.
                    "LOCALAPPDATA": shell.SHGetFolderPath(
                        0, shellcon.CSIDL_LOCAL_APPDATA, None, 0
                    ),
                    "APPDATA": str(workspace),
                    "PATH": os.pathsep.join(
                        str(p)
                        for p in (
                            Path(sys.executable).parent,
                            *runtimes,
                            Path(win32api.GetSystemDirectory()),
                        )
                    ),
                    "TEMP": str(workspace),
                    "TMP": str(workspace),
                    "USERPROFILE": str(workspace),
                    "HOME": str(workspace),
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PATHEXT": ".COM;.EXE;.BAT;.CMD",
                }
            )
            environment = ctypes.create_unicode_buffer(
                "\0".join(f"{k}={v}" for k, v in sorted(child_env.items())) + "\0\0"
            )
            info = _ProcessInfo()
            command_line = subprocess.list2cmdline(argv)
            command = ctypes.create_unicode_buffer(command_line)
            if not _kernel.CreateProcessW(
                argv[0],
                command,
                None,
                None,
                True,
                0x80000 | 0x400 | 0x4 | 0x08000000,
                environment,
                str(workspace),
                ctypes.byref(startup),
                ctypes.byref(info),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            process, thread = (
                pywintypes.HANDLE(info.process),
                pywintypes.HANDLE(info.thread),
            )
            resources.callback(process.Close)
            launch.callback(thread.Close)
            try:
                win32job.AssignProcessToJobObject(job, process)
                win32process.ResumeThread(thread)
            except BaseException:
                # Assignment may fail before the job owns this suspended process.
                win32process.TerminateProcess(process, 1)
                win32event.WaitForSingleObject(process, win32event.INFINITE)
                raise
            return WindowsSandboxProcess(
                process, job, info.pid, stdin, stdout, stderr, resources.pop_all()
            )

    def run(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        output_limit: int | None = None,
        discard_stdout: bool = False,
    ) -> SandboxRunResult:
        """Run synchronously with bounded output and job-wide timeout cleanup.

        Args:
            argv: Executable and arguments.
            spec: Sandbox policy.
            env: Explicit environment additions.
            timeout: Maximum wall-clock seconds.
            output_limit: Maximum captured bytes per stream.
            discard_stdout: Whether stdout should be discarded.

        Returns:
            Captured output and exit status.

        Raises:
            SandboxTimeoutError: If the job exceeds the wall-clock timeout.
        """
        if output_limit is not None and output_limit < 1:
            raise ValueError("Sandbox output limit must be positive.")
        process = self._spawn(argv, spec, env)
        outputs = [bytearray(), bytearray()]
        limited = [False, False]

        def capture(index, pipe):
            while chunk := pipe.file.read(8192):
                if index == 0 and discard_stdout:
                    continue
                remaining = (
                    len(chunk)
                    if output_limit is None
                    else max(0, output_limit - len(outputs[index]))
                )
                outputs[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    limited[index] = True
                    process.kill()

        readers = [
            threading.Thread(target=capture, args=(i, pipe), daemon=True)
            for i, pipe in enumerate((process.stdout, process.stderr))
        ]
        try:
            process.stdin.file.close()
            for reader in readers:
                reader.start()
            result = win32event.WaitForSingleObject(
                process.process,
                win32event.INFINITE if timeout is None else max(1, int(timeout * 1000)),
            )
            if result == win32event.WAIT_TIMEOUT:
                raise SandboxTimeoutError(
                    f"Sandbox command timed out after {timeout} seconds."
                )
            returncode = process.returncode
        finally:
            process.kill()
            for reader in readers:
                if reader.ident is not None:
                    reader.join()
            process.close()
        return SandboxRunResult(
            returncode, bytes(outputs[0]), bytes(outputs[1]), *limited
        )

    async def spawn_shell(
        self,
        command: str,
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> WindowsSandboxProcess:
        """Start PowerShell on a workspace PSDrive with managed pipes.

        Args:
            command: PowerShell command text.
            spec: Sandbox policy.
            env: Explicit environment additions.

        Returns:
            A managed Windows sandbox process.
        """
        from .windows_setup import shell_path

        # PowerShell's normal Set-Location walks unauthorized ancestors. A
        # provider drive rooted at the workspace needs no ancestor ACL grants.
        script = (
            "$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = "
            "[System.Text.UTF8Encoding]::new($false);\n"
            "try {\n"
            "New-PSDrive -Name Workspace -PSProvider FileSystem -Root $env:HOME "
            "-ErrorAction Stop | Out-Null;\n"
            "Set-Location -LiteralPath 'Workspace:\\' -ErrorAction Stop;\n"
            "} catch { Write-Error $_; exit 1 };\n" + command
        )
        # Keep ownership through cancellation of the asynchronous caller.
        task = asyncio.create_task(
            asyncio.to_thread(
                self._spawn,
                [
                    str(shell_path()),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-InputFormat",
                    "Text",
                    "-OutputFormat",
                    "Text",
                    "-EncodedCommand",
                    base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
                ],
                spec,
                env,
                merge_output=True,
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            process = await task
            await asyncio.to_thread(process.close)
            raise
