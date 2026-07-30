from __future__ import annotations

import asyncio
import hashlib
import locale
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info < (3, 14):
    from python_ripgrep import search

from astrbot.api import logger
from astrbot.core.computer.file_read_utils import (
    detect_text_encoding,
    read_local_text_range_sync,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_root,
    get_astrbot_system_tmp_path,
)

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .shipyard_search_file_util import _truncate_long_lines

_BLOCKED_COMMAND_PATTERNS = [
    " rm -rf ",
    " rm -fr ",
    " rm -r ",
    " mkfs",
    " dd if=",
    " shutdown",
    " reboot",
    " poweroff",
    " halt",
    " sudo ",
    ":(){:|:&};:",
    " kill -9 ",
    " killall ",
]
_LINUX_SANDBOX_MAX_CPU_SECONDS = 300
_LINUX_SANDBOX_MAX_FILE_BYTES = 100 * 1024 * 1024
_LINUX_SANDBOX_MAX_MEMORY_BYTES = 1024 * 1024 * 1024
_LINUX_SANDBOX_MAX_OPEN_FILES = 256
_LINUX_SANDBOX_MAX_PROCESSES = 256
_LINUX_SANDBOX_MAX_OUTPUT_BYTES = 10 * 1024 * 1024
_LINUX_SANDBOX_TMP_BYTES = 256 * 1024 * 1024
_LINUX_SANDBOX_LIMIT_LAUNCHER = f"""
import os
import resource
import sys

limits = (
    (resource.RLIMIT_CPU, {_LINUX_SANDBOX_MAX_CPU_SECONDS}),
    (resource.RLIMIT_FSIZE, {_LINUX_SANDBOX_MAX_FILE_BYTES}),
    (resource.RLIMIT_AS, {_LINUX_SANDBOX_MAX_MEMORY_BYTES}),
    (resource.RLIMIT_NOFILE, {_LINUX_SANDBOX_MAX_OPEN_FILES}),
    (resource.RLIMIT_NPROC, {_LINUX_SANDBOX_MAX_PROCESSES}),
    (resource.RLIMIT_CORE, 0),
)
for kind, requested in limits:
    _, hard = resource.getrlimit(kind)
    value = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (value, value))
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
"""


def _is_safe_command(command: str) -> bool:
    cmd = f" {command.strip().lower()} "
    return not any(pat in cmd for pat in _BLOCKED_COMMAND_PATTERNS)


def _build_linux_bwrap_command(
    argv: list[str],
    *,
    workspace: Path,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Build a fail-closed bubblewrap command for non-admin Local execution.

    Args:
        argv: Command and arguments to execute inside the sandbox.
        workspace: Only host directory mounted read-write.
        env: Additional environment variables exposed inside the sandbox.

    Returns:
        Bubblewrap arguments with namespace, mount, and resource restrictions.

    Raises:
        RuntimeError: If Linux, bubblewrap, or the workspace is unavailable.
        ValueError: If no command was provided.
    """
    if not argv:
        raise ValueError("A sandbox command is required.")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("The Local bubblewrap sandbox is only available on Linux.")
    bwrap_path = shutil.which("bwrap")
    if not bwrap_path:
        raise RuntimeError(
            "bubblewrap (`bwrap`) is required for non-admin Local execution."
        )

    resolved_workspace = workspace.resolve()
    if not resolved_workspace.is_dir():
        raise RuntimeError(f"Sandbox workspace does not exist: {resolved_workspace}")
    if not Path("/bin/sh").exists():
        raise RuntimeError("The Local bubblewrap sandbox requires /bin/sh.")

    readonly_paths = {
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/lib"),
        Path("/lib64"),
        Path("/etc/alternatives"),
        Path("/etc/ld.so.cache"),
        Path("/etc/ld.so.conf"),
        Path("/etc/ld.so.conf.d"),
        Path("/etc/localtime"),
        Path("/etc/nsswitch.conf"),
        Path("/etc/passwd"),
        Path("/etc/group"),
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
    }
    readonly_paths = {path for path in readonly_paths if path.exists()}

    required_directories = {Path("/tmp"), Path("/tmp/home")}
    for path in (*readonly_paths, resolved_workspace):
        required_directories.update(
            parent
            for parent in path.parents
            if parent != Path("/") and parent not in readonly_paths
        )

    command = [
        bwrap_path,
        "--unshare-all",
        "--new-session",
        "--die-with-parent",
        "--clearenv",
        "--dir",
        "/tmp",
        "--size",
        str(_LINUX_SANDBOX_TMP_BYTES),
        "--tmpfs",
        "/tmp",
    ]
    for directory in sorted(required_directories, key=lambda path: len(path.parts)):
        if directory == Path("/tmp"):
            continue
        command.extend(("--dir", str(directory)))
    command.extend(("--proc", "/proc", "--dev", "/dev"))

    for path in sorted(readonly_paths, key=lambda item: len(item.parts)):
        if path.is_symlink():
            command.extend(("--symlink", os.readlink(path), str(path)))
        else:
            command.extend(("--ro-bind", str(path), str(path)))

    command.extend(
        (
            "--bind",
            str(resolved_workspace),
            str(resolved_workspace),
            "--chdir",
            str(resolved_workspace),
        )
    )
    for key, value in sorted((env or {}).items()):
        command.extend(("--setenv", str(key), str(value)))
    command.extend(
        (
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/tmp/home",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--",
            sys.executable,
            "-I",
            "-S",
            "-c",
            _LINUX_SANDBOX_LIMIT_LAUNCHER,
            *argv,
        )
    )
    return command


def _decode_bytes_with_fallback(
    output: bytes | None,
    *,
    preferred_encoding: str | None = None,
) -> str:
    if output is None:
        return ""

    preferred = locale.getpreferredencoding(False) or "utf-8"
    attempted_encodings: list[str] = []

    def _try_decode(encoding: str) -> str | None:
        normalized = encoding.lower()
        if normalized in attempted_encodings:
            return None
        attempted_encodings.append(normalized)
        try:
            return output.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            return None

    for encoding in filter(None, [preferred_encoding, "utf-8", "utf-8-sig"]):
        if decoded := _try_decode(encoding):
            return decoded

    if os.name == "nt":
        for encoding in ("mbcs", "cp936", "gbk", "gb18030", preferred):
            if decoded := _try_decode(encoding):
                return decoded
    elif decoded := _try_decode(preferred):
        return decoded

    return output.decode("utf-8", errors="replace")


def _decode_shell_output(output: bytes | None) -> str:
    return _decode_bytes_with_fallback(output, preferred_encoding="utf-8")


@dataclass
class _LocalShellSession:
    """Runtime state for one managed local shell process."""

    session_id: str
    owner_id: str
    process: asyncio.subprocess.Process
    output_path: Path
    started_at: float
    output_event: asyncio.Event
    reader_task: asyncio.Task[None]
    wait_task: asyncio.Task[int]
    timeout_task: asyncio.Task[None] | None = None
    cursor: int = 0
    timed_out: bool = False
    terminated: bool = False
    output_limited: bool = False


@dataclass
class LocalShellComponent(ShellComponent):
    _sessions: dict[str, _LocalShellSession] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _sessions_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
        repr=False,
    )

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")

        def _run() -> dict[str, Any]:
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})
            working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
            popen_command: str | list[str] = command
            popen_shell = shell
            if sys.platform == "win32" and shell:
                popen_command = [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                ]
                popen_shell = False
            if background:
                # Shell commands use PowerShell 5.1 on Windows and the platform
                # shell elsewhere. Safety relies on `_is_safe_command()`.
                proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    popen_command,
                    shell=popen_shell,
                    cwd=working_dir,
                    env=run_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}
            # Shell commands use PowerShell 5.1 on Windows and the platform shell
            # elsewhere. Safety relies on `_is_safe_command()`.
            proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                popen_command,
                shell=popen_shell,
                cwd=working_dir,
                env=run_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout or 300)
            except subprocess.TimeoutExpired:
                should_kill_parent = sys.platform != "win32"
                if sys.platform == "win32":
                    try:
                        taskkill_result = subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                        should_kill_parent = taskkill_result.returncode != 0
                    except Exception:
                        should_kill_parent = True
                if should_kill_parent:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                raise
            return {
                "stdout": _decode_shell_output(stdout),
                "stderr": _decode_shell_output(stderr),
                "exit_code": proc.returncode,
            }

        return await asyncio.to_thread(_run)

    async def exec_managed(
        self,
        command: str,
        *,
        owner_id: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        yield_time_ms: int = 10_000,
        max_output_chars: int = 10_000,
        sandboxed: bool = False,
    ) -> dict[str, Any]:
        """Start a locally managed shell process and briefly wait for it.

        Args:
            command: Shell command to execute.
            owner_id: Unified message origin that owns the process.
            cwd: Working directory for the process.
            env: Additional environment variables.
            timeout: Hard process lifetime in seconds. None disables it.
            yield_time_ms: Maximum time to wait before returning a session ID.
            max_output_chars: Maximum output bytes returned in this call.
            sandboxed: Whether to isolate the command with Linux bubblewrap.

        Returns:
            Process result with output, status, and session metadata.

        Raises:
            PermissionError: If the command matches a blocked pattern.
            RuntimeError: If the requested bubblewrap sandbox is unavailable.
            ValueError: If a timing or output limit is invalid.
        """
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")
        if yield_time_ms < 0 or yield_time_ms > 30_000:
            raise ValueError("`yield_time_ms` must be between 0 and 30000.")
        if timeout is not None and timeout <= 0:
            raise ValueError("`timeout` must be greater than 0 when provided.")
        if max_output_chars < 1:
            raise ValueError("`max_output_chars` must be greater than 0.")

        working_dir = Path(cwd).resolve() if cwd else Path(get_astrbot_root()).resolve()
        if sandboxed:
            process_args = tuple(
                _build_linux_bwrap_command(
                    ["/bin/sh", "-c", command],
                    workspace=working_dir,
                    env={str(k): str(v) for k, v in (env or {}).items()},
                )
            )
            process_factory = asyncio.create_subprocess_exec
            run_env = {"PATH": os.defpath}
        else:
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})
        session_id = f"sh_{uuid.uuid4().hex[:16]}"
        owner_digest = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:16]
        output_dir = Path(get_astrbot_system_tmp_path()) / "shell" / owner_digest
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{session_id}.log"
        output_path.touch()

        process_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            process_kwargs["creationflags"] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )
        else:
            process_kwargs["start_new_session"] = True

        try:
            if not sandboxed:
                if sys.platform == "win32":
                    process_factory = asyncio.create_subprocess_exec
                    process_args = (
                        "powershell.exe",
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        command,
                    )
                else:
                    process_factory = asyncio.create_subprocess_shell
                    process_args = (command,)
            process = await process_factory(
                *process_args,
                cwd=working_dir,
                env=run_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **process_kwargs,
            )
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

        output_event = asyncio.Event()

        async def _capture_output() -> None:
            if process.stdout is None:
                return
            output_size = 0
            with output_path.open("ab") as output_file:
                while chunk := await process.stdout.read(8192):
                    if sandboxed:
                        remaining = _LINUX_SANDBOX_MAX_OUTPUT_BYTES - output_size
                        if remaining <= 0:
                            session.output_limited = True
                            try:
                                os.killpg(process.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                            return
                        if len(chunk) > remaining:
                            chunk = chunk[:remaining]
                            session.output_limited = True
                    output_file.write(chunk)
                    output_file.flush()
                    output_size += len(chunk)
                    output_event.set()
                    if session.output_limited:
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        return

        reader_task = asyncio.create_task(
            _capture_output(),
            name=f"local_shell_output_{session_id}",
        )
        wait_task = asyncio.create_task(
            process.wait(),
            name=f"local_shell_wait_{session_id}",
        )
        wait_task.add_done_callback(lambda _: output_event.set())
        session = _LocalShellSession(
            session_id=session_id,
            owner_id=owner_id,
            process=process,
            output_path=output_path,
            started_at=time.time(),
            output_event=output_event,
            reader_task=reader_task,
            wait_task=wait_task,
        )

        if timeout is not None:

            async def _enforce_timeout() -> None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(wait_task),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    session.timed_out = True
                    logger.warning(
                        "Managed local shell session timed out: session_id=%s pid=%s",
                        session_id,
                        process.pid,
                    )
                    await self._terminate_process(session)

            session.timeout_task = asyncio.create_task(
                _enforce_timeout(),
                name=f"local_shell_timeout_{session_id}",
            )

        async with self._sessions_lock:
            self._sessions[session_id] = session

        if yield_time_ms > 0:
            try:
                await asyncio.wait_for(
                    asyncio.shield(wait_task),
                    timeout=yield_time_ms / 1000,
                )
            except asyncio.TimeoutError:
                pass

        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            cursor=0,
            yield_time_ms=0,
            max_output_chars=max_output_chars,
        )

    async def list_sessions(self, owner_id: str) -> dict[str, Any]:
        """List managed shell sessions owned by one conversation.

        Args:
            owner_id: Unified message origin that owns the sessions.

        Returns:
            Session summaries scoped to the owner.
        """
        async with self._sessions_lock:
            sessions = [
                session
                for session in self._sessions.values()
                if session.owner_id == owner_id
            ]

        items = []
        for session in sessions:
            exit_code = session.process.returncode
            status = (
                "running"
                if exit_code is None
                else (
                    "timed_out"
                    if session.timed_out
                    else (
                        "output_limited"
                        if session.output_limited
                        else (
                            "terminated"
                            if session.terminated
                            else ("completed" if exit_code == 0 else "failed")
                        )
                    )
                )
            )
            try:
                output_size = session.output_path.stat().st_size
            except OSError:
                output_size = session.cursor
            items.append(
                {
                    "session_id": session.session_id,
                    "pid": session.process.pid,
                    "status": status,
                    "exit_code": exit_code,
                    "started_at": session.started_at,
                    "unread_output_bytes": max(output_size - session.cursor, 0),
                }
            )
        return {"sessions": items}

    async def poll_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        cursor: int | None = None,
        yield_time_ms: int = 0,
        max_output_chars: int = 10_000,
    ) -> dict[str, Any]:
        """Read new output and status from a managed shell session.

        Args:
            owner_id: Unified message origin that owns the session.
            session_id: Managed shell session identifier.
            cursor: Byte offset to read from. Defaults to the last returned offset.
            yield_time_ms: Maximum wait for new output or process completion.
            max_output_chars: Maximum output bytes returned in this call.

        Returns:
            Incremental output, next cursor, process status, and exit code.

        Raises:
            ValueError: If the session is unavailable or an argument is invalid.
        """
        if yield_time_ms < 0 or yield_time_ms > 30_000:
            raise ValueError("`yield_time_ms` must be between 0 and 30000.")
        if max_output_chars < 1:
            raise ValueError("`max_output_chars` must be greater than 0.")

        session = await self._get_owned_session(owner_id, session_id)
        read_cursor = session.cursor if cursor is None else cursor
        if read_cursor < 0:
            raise ValueError("`cursor` must be greater than or equal to 0.")

        def _read_output() -> tuple[bytes, int, int]:
            try:
                output_size = session.output_path.stat().st_size
            except FileNotFoundError:
                return b"", read_cursor, read_cursor
            normalized_cursor = min(read_cursor, output_size)
            with session.output_path.open("rb") as output_file:
                output_file.seek(normalized_cursor)
                raw_output = output_file.read(max_output_chars)
            return (
                raw_output,
                normalized_cursor + len(raw_output),
                output_size,
            )

        if session.wait_task.done():
            await session.reader_task
        raw_output, next_cursor, output_size = await asyncio.to_thread(_read_output)

        if not raw_output and session.process.returncode is None and yield_time_ms > 0:
            session.output_event.clear()
            raw_output, next_cursor, output_size = await asyncio.to_thread(_read_output)
            if not raw_output and session.process.returncode is None:
                output_waiter = asyncio.create_task(session.output_event.wait())
                done, _ = await asyncio.wait(
                    {output_waiter, session.wait_task},
                    timeout=yield_time_ms / 1000,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if output_waiter not in done:
                    output_waiter.cancel()
                    try:
                        await output_waiter
                    except asyncio.CancelledError:
                        pass
                if session.wait_task.done():
                    await session.reader_task
                raw_output, next_cursor, output_size = await asyncio.to_thread(
                    _read_output
                )

        exit_code = session.process.returncode
        if exit_code is not None:
            await session.reader_task
            raw_output, next_cursor, output_size = await asyncio.to_thread(_read_output)

        exit_code = session.process.returncode
        if exit_code is not None and not session.reader_task.done():
            await session.reader_task
            raw_output, next_cursor, output_size = await asyncio.to_thread(_read_output)

        session.cursor = next_cursor
        status = (
            "running"
            if exit_code is None
            else (
                "timed_out"
                if session.timed_out
                else (
                    "output_limited"
                    if session.output_limited
                    else (
                        "terminated"
                        if session.terminated
                        else ("completed" if exit_code == 0 else "failed")
                    )
                )
            )
        )
        has_more = next_cursor < output_size
        session_closed = exit_code is not None and not has_more
        result = {
            "session_id": session.session_id,
            "pid": session.process.pid,
            "status": status,
            "stdout": _decode_shell_output(raw_output),
            "stderr": "",
            "exit_code": exit_code,
            "cursor": next_cursor,
            "has_more": has_more,
            "session_closed": session_closed,
        }
        if session_closed:
            await self._remove_session(session)
        return result

    async def write_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        chars: str,
    ) -> dict[str, Any]:
        """Write text to the stdin pipe of a managed shell session.

        Args:
            owner_id: Unified message origin that owns the session.
            session_id: Managed shell session identifier.
            chars: Text to write verbatim.

        Returns:
            Current process status after the write.

        Raises:
            ValueError: If the session is unavailable or no longer accepts input.
        """
        session = await self._get_owned_session(owner_id, session_id)
        if session.process.returncode is not None or session.process.stdin is None:
            raise ValueError(f"Shell session {session_id} is not accepting input.")
        session.process.stdin.write(chars.encode("utf-8"))
        await session.process.stdin.drain()
        return {
            "session_id": session_id,
            "pid": session.process.pid,
            "status": "running",
            "written_chars": len(chars),
        }

    async def interrupt_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        yield_time_ms: int = 1_000,
        max_output_chars: int = 10_000,
    ) -> dict[str, Any]:
        """Send an interrupt signal to a managed shell process group.

        Args:
            owner_id: Unified message origin that owns the session.
            session_id: Managed shell session identifier.
            yield_time_ms: Maximum wait for output or exit after the signal.
            max_output_chars: Maximum output bytes returned after the signal.

        Returns:
            Incremental output and status after sending the interrupt.
        """
        session = await self._get_owned_session(owner_id, session_id)
        if session.process.returncode is None:
            if os.name == "nt":
                session.process.send_signal(
                    getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM)
                )
            else:
                try:
                    os.killpg(session.process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            yield_time_ms=yield_time_ms,
            max_output_chars=max_output_chars,
        )

    async def terminate_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        max_output_chars: int = 10_000,
    ) -> dict[str, Any]:
        """Terminate a managed shell process group.

        Args:
            owner_id: Unified message origin that owns the session.
            session_id: Managed shell session identifier.
            max_output_chars: Maximum remaining output bytes to return.

        Returns:
            Remaining output and final process status.
        """
        session = await self._get_owned_session(owner_id, session_id)
        session.terminated = True
        await self._terminate_process(session)
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            yield_time_ms=0,
            max_output_chars=max_output_chars,
        )

    async def shutdown_sessions(self) -> None:
        """Terminate and remove every managed local shell session."""
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.terminated = True
        termination_results = await asyncio.gather(
            *(self._terminate_process(session) for session in sessions),
            return_exceptions=True,
        )
        for session, result in zip(sessions, termination_results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to terminate managed local shell session %s: %s",
                    session.session_id,
                    result,
                )
        await asyncio.gather(
            *(session.reader_task for session in sessions),
            return_exceptions=True,
        )
        for session in sessions:
            await self._remove_session(session)

    async def _get_owned_session(
        self,
        owner_id: str,
        session_id: str,
    ) -> _LocalShellSession:
        """Resolve a shell session while enforcing conversation ownership.

        Args:
            owner_id: Unified message origin that must own the session.
            session_id: Managed shell session identifier.

        Returns:
            Matching managed shell session.

        Raises:
            ValueError: If the session does not exist for this owner.
        """
        async with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None or session.owner_id != owner_id:
            raise ValueError(f"Shell session {session_id} was not found.")
        return session

    async def _terminate_process(self, session: _LocalShellSession) -> None:
        """Gracefully terminate a process group, then force it if needed.

        Args:
            session: Managed shell session to terminate.
        """
        if session.process.returncode is not None:
            return
        if os.name == "nt":
            try:
                taskkill_result = await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/T", "/PID", str(session.process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                session.process.terminate()
            else:
                if taskkill_result.returncode != 0:
                    session.process.terminate()
        else:
            try:
                os.killpg(session.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        try:
            await asyncio.wait_for(
                asyncio.shield(session.wait_task),
                timeout=5,
            )
        except asyncio.TimeoutError:
            if os.name == "nt":
                session.process.kill()
            else:
                try:
                    os.killpg(session.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await session.wait_task

    async def _remove_session(self, session: _LocalShellSession) -> None:
        """Remove a completed session and its temporary output file.

        Args:
            session: Managed shell session to remove.
        """
        async with self._sessions_lock:
            if self._sessions.get(session.session_id) is session:
                self._sessions.pop(session.session_id, None)
        timeout_task = session.timeout_task
        if (
            timeout_task is not None
            and timeout_task is not asyncio.current_task()
            and not timeout_task.done()
        ):
            timeout_task.cancel()
            try:
                await timeout_task
            except asyncio.CancelledError:
                pass
        session.output_path.unlink(missing_ok=True)
        try:
            session.output_path.parent.rmdir()
        except OSError:
            pass


@dataclass
class LocalPythonComponent(PythonComponent):
    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
        cwd: str | None = None,
        sandboxed: bool = False,
    ) -> dict[str, Any]:
        """Execute Python locally, optionally inside the Linux sandbox.

        Args:
            code: Python source to execute.
            kernel_id: Reserved kernel identifier for protocol compatibility.
            timeout: Hard execution timeout in seconds.
            silent: Whether to suppress standard output.
            cwd: Working directory for the process.
            sandboxed: Whether to isolate execution with Linux bubblewrap.

        Returns:
            Python output and error data in the computer component format.
        """

        def _run() -> dict[str, Any]:
            try:
                working_dir = (
                    Path(cwd).resolve() if cwd else Path(get_astrbot_root()).resolve()
                )
                if sandboxed:
                    run_command = _build_linux_bwrap_command(
                        [sys.executable, "-c", code],
                        workspace=working_dir,
                    )
                    run_env = {"PATH": os.defpath}
                    with (
                        tempfile.TemporaryFile() as stdout_file,
                        tempfile.TemporaryFile() as stderr_file,
                    ):
                        result = subprocess.run(
                            run_command,
                            timeout=timeout,
                            stdout=subprocess.DEVNULL if silent else stdout_file,
                            stderr=stderr_file,
                            cwd=working_dir,
                            env=run_env,
                        )
                        if silent:
                            stdout = ""
                            stdout_limited = False
                        else:
                            stdout_file.seek(0)
                            stdout_bytes = stdout_file.read(
                                _LINUX_SANDBOX_MAX_OUTPUT_BYTES + 1
                            )
                            stdout_limited = (
                                len(stdout_bytes) > _LINUX_SANDBOX_MAX_OUTPUT_BYTES
                            )
                            stdout = _decode_shell_output(
                                stdout_bytes[:_LINUX_SANDBOX_MAX_OUTPUT_BYTES]
                            )
                        stderr_file.seek(0)
                        stderr_bytes = stderr_file.read(
                            _LINUX_SANDBOX_MAX_OUTPUT_BYTES + 1
                        )
                        stderr_limited = (
                            len(stderr_bytes) > _LINUX_SANDBOX_MAX_OUTPUT_BYTES
                        )
                        stderr = _decode_shell_output(
                            stderr_bytes[:_LINUX_SANDBOX_MAX_OUTPUT_BYTES]
                        )
                else:
                    run_command = [
                        os.environ.get("PYTHON", sys.executable),
                        "-c",
                        code,
                    ]
                    run_env = None
                    result = subprocess.run(
                        run_command,
                        timeout=timeout,
                        capture_output=True,
                        cwd=working_dir,
                        env=run_env,
                    )
                    stdout = "" if silent else _decode_shell_output(result.stdout)
                    stderr = _decode_shell_output(result.stderr)
                    stdout_limited = False
                    stderr_limited = False
                if stdout_limited or stderr_limited:
                    limit_error = (
                        "Execution output exceeded "
                        f"{_LINUX_SANDBOX_MAX_OUTPUT_BYTES} bytes."
                    )
                    stderr = f"{stderr}\n{limit_error}".strip()
                execution_error = (
                    stderr
                    if result.returncode != 0 or stdout_limited or stderr_limited
                    else ""
                )
                return {
                    "data": {
                        "output": {"text": stdout, "images": []},
                        "error": execution_error,
                    }
                }
            except subprocess.TimeoutExpired:
                return {
                    "data": {
                        "output": {"text": "", "images": []},
                        "error": "Execution timed out.",
                    }
                }

        return await asyncio.to_thread(_run)


@dataclass
class LocalFileSystemComponent(FileSystemComponent):
    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(abs_path, mode)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            detected_encoding = encoding
            if encoding == "utf-8":
                with open(abs_path, "rb") as f:
                    raw_sample = f.read(8192)
                detected_encoding = detect_text_encoding(raw_sample) or encoding
            return {
                "success": True,
                "content": read_local_text_range_sync(
                    abs_path,
                    encoding=detected_encoding,
                    offset=offset,
                    limit=limit,
                ),
            }

        return await asyncio.to_thread(_run)

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            if sys.version_info < (3, 14):
                results = search(
                    patterns=[pattern],
                    paths=[path] if path else None,
                    globs=[glob] if glob else None,
                    after_context=after_context,
                    before_context=before_context,
                    line_number=True,
                )
                return {
                    "success": True,
                    "content": _truncate_long_lines("".join(results)),
                }

            rg_path = shutil.which("rg")
            if not rg_path:
                return {
                    "success": False,
                    "content": "",
                    "error": (
                        "The ripgrep (rg) executable is required for file search on "
                        "Python 3.14 or later because python-ripgrep 0.0.8 is "
                        "incompatible."
                    ),
                }

            command = [rg_path, "--color=never", "-n", "-e", pattern]
            if glob:
                command.extend(["-g", glob])
            if after_context is not None:
                command.extend(["-A", str(after_context)])
            if before_context is not None:
                command.extend(["-B", str(before_context)])
            command.extend(["--", path or "."])

            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "content": "",
                    "error": "File search timed out after 30 seconds.",
                }
            except OSError as exc:
                return {
                    "success": False,
                    "content": "",
                    "error": f"Unable to start ripgrep: {exc}",
                }

            stdout = _decode_bytes_with_fallback(
                result.stdout, preferred_encoding="utf-8"
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "content": _truncate_long_lines(stdout),
                }
            if result.returncode == 1:
                return {"success": True, "content": ""}

            stderr = _decode_bytes_with_fallback(
                result.stderr, preferred_encoding="utf-8"
            ).strip()
            return {
                "success": False,
                "content": "",
                "error": stderr or f"ripgrep exited with code {result.returncode}",
                "exit_code": result.returncode,
            }

        return await asyncio.to_thread(_run)

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            with open(abs_path, encoding=encoding) as f:
                content = f.read()
            occurrences = content.count(old_string)
            if occurrences == 0:
                return {
                    "success": False,
                    "error": "old string not found in file",
                    "replacements": 0,
                }
            if replace_all:
                updated = content.replace(old_string, new_string)
                replacements = occurrences
            else:
                updated = content.replace(old_string, new_string, 1)
                replacements = 1
            with open(abs_path, "w", encoding=encoding) as f:
                f.write(updated)
            return {
                "success": True,
                "path": abs_path,
                "replacements": replacements,
            }

        return await asyncio.to_thread(_run)

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, mode, encoding=encoding) as f:
                f.write(content)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def delete_file(self, path: str) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            if os.path.isdir(abs_path):
                shutil.rmtree(abs_path)
            else:
                os.remove(abs_path)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            entries = os.listdir(abs_path)
            if not show_hidden:
                entries = [e for e in entries if not e.startswith(".")]
            return {"success": True, "entries": entries}

        return await asyncio.to_thread(_run)


class LocalBooter(ComputerBooter):
    def __init__(self) -> None:
        self._fs = LocalFileSystemComponent()
        self._python = LocalPythonComponent()
        self._shell = LocalShellComponent()

    async def boot(self, session_id: str) -> None:
        logger.info(f"Local computer booter initialized for session: {session_id}")

    async def shutdown(self) -> None:
        await self._shell.shutdown_sessions()
        logger.info("Local computer booter shutdown complete.")

    @property
    def fs(self) -> FileSystemComponent:
        return self._fs

    @property
    def python(self) -> PythonComponent:
        return self._python

    @property
    def shell(self) -> ShellComponent:
        return self._shell

    async def upload_file(self, path: str, file_name: str) -> dict:
        raise NotImplementedError(
            "LocalBooter does not support upload_file operation. Use shell instead."
        )

    async def download_file(self, remote_path: str, local_path: str) -> None:
        raise NotImplementedError(
            "LocalBooter does not support download_file operation. Use shell instead."
        )

    async def available(self) -> bool:
        return True
