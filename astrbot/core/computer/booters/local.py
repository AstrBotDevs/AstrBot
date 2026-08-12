import asyncio
import fnmatch
import hashlib
import locale
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot import logger
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
    re.compile(r"(^|[;&|() ])rm(?:\.exe)?\s+-[a-z-]*r[a-z-]*(?:\s|$)"),
    re.compile(r"(^|[;&|() ])mkfs(?:\.[a-z0-9_+-]+)?(?:\s|$)"),
    re.compile(r"(^|[;&|() ])dd\s+if="),
    re.compile(r"(^|[;&|() ])(?:shutdown|reboot|poweroff|halt)(?:\s|$)"),
    re.compile(r"(^|[;&|() ])sudo(?:\s|$)"),
    re.compile(r"(^|[;&|() ])kill\s+-9(?:\s|$)"),
    re.compile(r"(^|[;&|() ])killall(?:\s|$)"),
]


def _is_safe_command(command: str) -> bool:
    normalized_command = re.sub(r"\s+", " ", command.strip().lower())
    if ":(){:|:&};:" in normalized_command:
        return False
    return not any(
        pattern.search(normalized_command) for pattern in _BLOCKED_COMMAND_PATTERNS
    )


def resolve_windows_shell() -> str:
    """Resolve PowerShell 7 when available, with the inbox fallback."""
    for candidate in ("pwsh", "powershell.exe"):
        try:
            resolved = shutil.which(candidate)
        except AttributeError, OSError:
            resolved = None
        if resolved:
            return resolved
    return "powershell.exe"


def _decode_bytes_with_fallback(
    output: bytes | str | None,
    *,
    preferred_encoding: str | None = None,
) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output

    preferred = locale.getpreferredencoding(False) or "utf-8"
    attempted_encodings: list[str] = []

    def _try_decode(encoding: str) -> str | None:
        normalized = encoding.lower()
        if normalized in attempted_encodings:
            return None
        attempted_encodings.append(normalized)
        try:
            return output.decode(encoding)
        except LookupError, UnicodeDecodeError:
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


def _decode_shell_output(output: bytes | str | None) -> str:
    return _decode_bytes_with_fallback(output, preferred_encoding="utf-8")


@dataclass
class LocalShellComponent(ShellComponent):
    _sessions: dict[str, _LocalShellSession] = field(default_factory=dict, init=False)
    _sessions_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    max_sessions: int = 16
    max_output_bytes: int = 4 * 1024 * 1024
    session_ttl_seconds: int = 30 * 60
    disk_quota_bytes: int = 32 * 1024 * 1024

    async def exec(  # noqa: ASYNC109
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
        timeout_seconds: int | None = 300,
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
                    resolve_windows_shell(),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                ]
                popen_shell = False
            popen_kwargs: dict[str, Any] = {
                "shell": popen_shell,
                "cwd": working_dir,
                "env": run_env,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                )
            else:
                popen_kwargs["start_new_session"] = True
            if background:
                # `command` is intentionally executed through the current shell so
                # local computer-use behavior matches existing tool semantics.
                # Safety relies on `_is_safe_command()` and the allowed-root checks.
                proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    popen_command,
                    # Controlled local computer-use command.
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **popen_kwargs,  # nosec B602
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}
            # `command` is intentionally executed through the current shell so
            # local computer-use behavior matches existing tool semantics.
            # Safety relies on `_is_safe_command()` and the allowed-root checks.
            proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                popen_command,
                # Controlled local computer-use command.
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_kwargs,  # nosec B602
            )
            effective_timeout = timeout if timeout is not None else timeout_seconds
            try:
                stdout, stderr = proc.communicate(timeout=effective_timeout or 300)
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
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                        should_kill_parent = False
                    except OSError:
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
        timeout: int | None = None,  # noqa: ASYNC109
        yield_time_ms: int = 10_000,
        max_output_chars: int = 10_000,
        runtime_id: str = "local",
        sender_id: str = "",
        allowed_root: str | None = None,
    ) -> dict[str, Any]:  # noqa: ASYNC109
        """Start a runtime-owned interactive shell session."""
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")
        if not 0 <= yield_time_ms <= 30_000:
            raise ValueError("yield_time_ms must be between 0 and 30000")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        max_output_chars = max(1, min(max_output_chars, 100_000))
        async with self._sessions_lock:
            if len(self._sessions) >= self.max_sessions:
                raise ValueError("Managed shell session limit reached")

        working_dir = Path(cwd or get_astrbot_root()).resolve(strict=False)
        boundary = Path(allowed_root or get_astrbot_root()).resolve(strict=False)
        if not working_dir.is_relative_to(boundary):
            raise PermissionError("Shell cwd is outside the allowed workspace")
        working_dir.mkdir(parents=True, exist_ok=True)
        owner_runtime_id = str(runtime_id or "local")
        owner_sender_id = str(sender_id or "")
        session_id = f"sh_{uuid.uuid4().hex[:16]}"
        owner_digest = hashlib.sha256(
            f"{owner_runtime_id}\0{owner_id}\0{owner_sender_id}".encode()
        ).hexdigest()[:16]
        output_dir = Path(get_astrbot_system_tmp_path()) / "shell" / owner_digest
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            current_usage = sum(
                path.stat().st_size
                for path in output_dir.parent.rglob("*.log")
                if path.is_file()
            )
        except OSError:
            current_usage = self.disk_quota_bytes
        if current_usage >= self.disk_quota_bytes:
            raise ValueError("Managed shell disk quota exceeded")
        output_path = output_dir / f"{session_id}.log"
        output_path.touch()

        process_kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "cwd": str(working_dir),
            "env": {**os.environ, **{str(k): str(v) for k, v in (env or {}).items()}},
        }
        if sys.platform == "win32":
            process_kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            process_kwargs["start_new_session"] = True
        try:
            if sys.platform == "win32":
                process = await asyncio.create_subprocess_exec(
                    resolve_windows_shell(),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                    **process_kwargs,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command, **process_kwargs
                )
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise

        output_event = asyncio.Event()

        async def capture_output() -> None:
            if process.stdout is None:
                return
            try:
                with output_path.open("ab") as output_file:
                    while chunk := await process.stdout.read(8192):
                        if output_path.stat().st_size >= self.max_output_bytes:
                            await self._terminate_process(process)
                            break
                        try:
                            total_usage = sum(
                                path.stat().st_size
                                for path in output_path.parent.parent.rglob("*.log")
                                if path.is_file()
                            )
                        except OSError:
                            total_usage = self.disk_quota_bytes
                        if total_usage >= self.disk_quota_bytes:
                            await self._terminate_process(process)
                            break
                        remaining = self.max_output_bytes - output_path.stat().st_size
                        remaining = min(
                            remaining,
                            self.disk_quota_bytes - total_usage,
                        )
                        output_file.write(chunk[:remaining])
                        output_file.flush()
                        output_event.set()
            except asyncio.CancelledError:
                raise

        reader_task = asyncio.create_task(
            capture_output(), name=f"shell-reader-{session_id}"
        )
        wait_task = asyncio.create_task(process.wait(), name=f"shell-wait-{session_id}")
        wait_task.add_done_callback(lambda _: output_event.set())
        session = _LocalShellSession(
            session_id=session_id,
            runtime_id=owner_runtime_id,
            umo=owner_id,
            sender_id=owner_sender_id,
            process=process,
            output_path=output_path,
            started_at=time.monotonic(),
            last_activity=time.monotonic(),
            output_event=output_event,
            reader_task=reader_task,
            wait_task=wait_task,
        )
        effective_ttl = timeout if timeout is not None else self.session_ttl_seconds
        if effective_ttl > 0:
            session.timeout_task = asyncio.create_task(
                self._timeout_session(session, effective_ttl),
                name=f"shell-timeout-{session_id}",
            )
        async with self._sessions_lock:
            self._sessions[session_id] = session
        if yield_time_ms:
            try:
                await asyncio.wait_for(asyncio.shield(wait_task), yield_time_ms / 1000)
            except TimeoutError:
                pass
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            yield_time_ms=0,
            max_output_chars=max_output_chars,
            runtime_id=owner_runtime_id,
            sender_id=owner_sender_id,
        )

    async def list_sessions(
        self,
        owner_id: str,
        *,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        sessions = await self._owned_sessions(owner_id, runtime_id, sender_id)
        return {"sessions": [self._session_summary(session) for session in sessions]}

    async def poll_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        cursor: int | None = None,
        yield_time_ms: int = 0,
        max_output_chars: int = 10_000,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        if not 0 <= yield_time_ms <= 30_000:
            raise ValueError("yield_time_ms must be between 0 and 30000")
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        session.last_activity = time.monotonic()
        read_cursor = session.cursor if cursor is None else max(0, cursor)

        async def read_output() -> tuple[bytes, int, int]:
            def _read() -> tuple[bytes, int, int]:
                try:
                    size = session.output_path.stat().st_size
                except OSError:
                    return b"", read_cursor, read_cursor
                start = min(read_cursor, size)
                with session.output_path.open("rb") as output_file:
                    output_file.seek(start)
                    data = output_file.read(max_output_chars)
                return data, start + len(data), size

            return await asyncio.to_thread(_read)

        data, next_cursor, size = await read_output()
        if not data and session.process.returncode is None and yield_time_ms:
            session.output_event.clear()
            waiter = asyncio.create_task(session.output_event.wait())
            try:
                await asyncio.wait(
                    {waiter, session.wait_task},
                    timeout=yield_time_ms / 1000,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not waiter.done():
                    waiter.cancel()
                    try:
                        await waiter
                    except asyncio.CancelledError:
                        pass
            if session.wait_task.done():
                await session.reader_task
            data, next_cursor, size = await read_output()
        if session.process.returncode is not None:
            await session.reader_task
            data, next_cursor, size = await read_output()
        session.cursor = next_cursor
        status = self._session_status(session)
        has_more = next_cursor < size
        result = {
            "session_id": session.session_id,
            "pid": session.process.pid,
            "status": status,
            "stdout": _decode_shell_output(data),
            "stderr": "",
            "exit_code": session.process.returncode,
            "cursor": next_cursor,
            "has_more": has_more,
            "session_closed": session.process.returncode is not None and not has_more,
        }
        if result["session_closed"]:
            await self._remove_session(session)
        return result

    async def write_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        chars: str,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        session.last_activity = time.monotonic()
        if session.process.returncode is not None or session.process.stdin is None:
            raise ValueError("Shell session is not accepting input")
        session.process.stdin.write(chars.encode("utf-8"))
        await session.process.stdin.drain()
        return {
            "session_id": session_id,
            "status": "running",
            "written_chars": len(chars),
        }

    async def interrupt_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        yield_time_ms: int = 1000,
        max_output_chars: int = 10000,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        if session.process.returncode is None:
            if sys.platform == "win32":
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
            runtime_id=runtime_id,
            sender_id=sender_id,
        )

    async def terminate_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        max_output_chars: int = 10000,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        session.terminated = True
        await self._terminate_process(session.process)
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            max_output_chars=max_output_chars,
            runtime_id=runtime_id,
            sender_id=sender_id,
        )

    async def shutdown_sessions(self) -> None:
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.terminated = True
        for session in sessions:
            await self._terminate_process(session.process)
        await asyncio.gather(*(session.reader_task for session in sessions))
        for session in sessions:
            await self._remove_session(session)

    async def _timeout_session(  # noqa: ASYNC109
        self,
        session: _LocalShellSession,
        timeout: int,  # noqa: ASYNC109
    ) -> None:
        try:
            while not session.wait_task.done():
                remaining = timeout - (time.monotonic() - session.last_activity)
                if remaining <= 0:
                    session.timed_out = True
                    await self._terminate_process(session.process)
                    return
                try:
                    await asyncio.wait_for(asyncio.shield(session.wait_task), remaining)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise

    async def _owned_sessions(
        self, owner_id: str, runtime_id: str, sender_id: str
    ) -> list[_LocalShellSession]:
        async with self._sessions_lock:
            return [
                session
                for session in self._sessions.values()
                if session.runtime_id == runtime_id
                and session.umo == owner_id
                and session.sender_id == sender_id
            ]

    async def _get_owned_session(
        self, session_id: str, owner_id: str, runtime_id: str, sender_id: str
    ) -> _LocalShellSession:
        async with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None or (session.runtime_id, session.umo, session.sender_id) != (
            runtime_id,
            owner_id,
            sender_id,
        ):
            raise ValueError("Shell session was not found")
        return session

    def _session_status(self, session: _LocalShellSession) -> str:
        if session.process.returncode is None:
            return "running"
        if session.timed_out:
            return "timed_out"
        if session.terminated:
            return "terminated"
        return "completed" if session.process.returncode == 0 else "failed"

    def _session_summary(self, session: _LocalShellSession) -> dict[str, Any]:
        try:
            size = session.output_path.stat().st_size
        except OSError:
            size = session.cursor
        return {
            "session_id": session.session_id,
            "pid": session.process.pid,
            "status": self._session_status(session),
            "exit_code": session.process.returncode,
            "started_at": session.started_at,
            "unread_output_bytes": max(0, size - session.cursor),
        }

    async def _remove_session(self, session: _LocalShellSession) -> None:
        async with self._sessions_lock:
            self._sessions.pop(session.session_id, None)
        if (
            session.timeout_task
            and not session.timeout_task.done()
            and session.timeout_task is not asyncio.current_task()
        ):
            session.timeout_task.cancel()
            try:
                await session.timeout_task
            except asyncio.CancelledError:
                pass
        session.output_path.unlink(missing_ok=True)
        try:
            session.output_path.parent.rmdir()
        except OSError:
            pass

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if sys.platform == "win32":
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                if result.returncode != 0:
                    process.terminate()
            except Exception:
                process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            if sys.platform == "win32":
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await process.wait()


@dataclass
class _LocalShellSession:
    session_id: str
    runtime_id: str
    umo: str
    sender_id: str
    process: asyncio.subprocess.Process
    output_path: Path
    started_at: float
    output_event: asyncio.Event
    reader_task: asyncio.Task
    wait_task: asyncio.Task
    last_activity: float
    timeout_task: asyncio.Task | None = None
    cursor: int = 0
    timed_out: bool = False
    terminated: bool = False


@dataclass
class LocalPythonComponent(PythonComponent):
    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout_seconds: int = 30,
        silent: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            try:
                working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
                result = subprocess.run(
                    [os.environ.get("PYTHON", sys.executable), "-c", code],
                    timeout=timeout_seconds,
                    capture_output=True,
                    cwd=working_dir,
                )
                stdout = "" if silent else _decode_shell_output(result.stdout)
                stderr = (
                    _decode_shell_output(result.stderr)
                    if result.returncode != 0
                    else ""
                )
                return {
                    "data": {
                        "output": {"text": stdout, "images": []},
                        "error": stderr,
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
            search_path = Path(path or get_astrbot_root()).resolve(strict=False)
            rg_path = shutil.which("rg")
            if rg_path:
                command = [
                    rg_path,
                    "--color=never",
                    "-n",
                    "--max-columns",
                    "1000",
                    "-e",
                    pattern,
                ]
                if glob:
                    command.extend(["-g", glob])
                if after_context is not None:
                    command.extend(["-A", str(after_context)])
                if before_context is not None:
                    command.extend(["-B", str(before_context)])
                command.extend(["--", str(search_path)])

                result = subprocess.run(
                    command,
                    capture_output=True,
                    cwd=get_astrbot_root(),
                )
                if result.returncode in (0, 1):
                    return {
                        "success": True,
                        "content": _truncate_long_lines(
                            _decode_shell_output(result.stdout)
                        ),
                    }
                return {
                    "success": False,
                    "content": "",
                    "error": _decode_shell_output(result.stderr)
                    or f"command exited with code {result.returncode}",
                    "exit_code": result.returncode,
                }

            matcher = re.compile(pattern)
            output_lines: list[str] = []
            paths = (
                [search_path]
                if search_path.is_file()
                else sorted(
                    path_ for path_ in search_path.rglob("*") if path_.is_file()
                )
            )
            for file_path in paths:
                if glob and not fnmatch.fnmatch(file_path.name, glob):
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                lines = text.splitlines()
                matching_indexes = [
                    index
                    for index, line in enumerate(lines)
                    if matcher.search(line) is not None
                ]
                if not matching_indexes:
                    continue

                if after_context is None and before_context is None:
                    for index in matching_indexes:
                        output_lines.append(
                            f"{file_path}:{index + 1}:{lines[index][:1000]}\n"
                        )
                    continue

                trailing = after_context or 0
                leading = before_context or 0
                ranges: list[tuple[int, int]] = []
                for index in matching_indexes:
                    start = max(0, index - leading)
                    end = min(len(lines) - 1, index + trailing)
                    if ranges and start <= ranges[-1][1] + 1:
                        ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
                    else:
                        ranges.append((start, end))

                for range_index, (start, end) in enumerate(ranges):
                    for line_index in range(start, end + 1):
                        output_lines.append(
                            f"{file_path}:{line_index + 1}:{lines[line_index][:1000]}\n"
                        )
                    if range_index != len(ranges) - 1:
                        output_lines.append("--\n")

            return {"success": True, "content": "".join(output_lines)}

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

    async def shutdown(self, **kwargs: Any) -> None:
        _ = kwargs
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
