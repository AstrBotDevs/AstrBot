"""
Local interactive shell component implementation.

Provides stateful bidirectional communication with shell processes using
subprocess.Popen with persistent stdin/stdout/stderr pipes.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import logger
from astrbot.core.computer.olayer.interactive_shell import (
    InteractiveSession,
    InteractiveSessionState,
    InteractiveShellComponent,
)
from astrbot.core.utils.astrbot_path import get_astrbot_root


@dataclass
class _LocalInteractiveSession:
    """Internal session state tracking."""

    session_id: str
    command: str
    process: subprocess.Popen
    stdout_buffer: bytearray = field(default_factory=bytearray)
    stderr_buffer: bytearray = field(default_factory=bytearray)
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_activity: float = field(default_factory=time.time)
    read_threads: list[threading.Thread] = field(default_factory=list)
    stop_reading: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.time)


class LocalInteractiveShellComponent(InteractiveShellComponent):
    """Local interactive shell implementation using subprocess.Popen.

    Maintains persistent processes with bidirectional communication.
    Uses background threads to continuously read process output into buffers,
    preventing pipe deadlocks.

    Implementation note: On Windows, subprocess pipes do not support
    line-buffering with text mode. We use binary mode and decode manually
    to ensure output is captured promptly.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _LocalInteractiveSession] = {}
        self._session_lock = threading.Lock()
        self._cleanup_task: asyncio.Task | None = None
        self._max_sessions = 10
        self._session_timeout_seconds = 1800  # 30 minutes

    async def _ensure_cleanup_task(self) -> None:
        """Ensure the periodic cleanup task is running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically clean up terminated and idle sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                self._cleanup_terminated()
                self._cleanup_idle_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[InteractiveShell] Cleanup error: %s", e)

    def _cleanup_terminated(self) -> None:
        """Remove sessions for processes that have exited."""
        to_remove: list[tuple[str, _LocalInteractiveSession]] = []
        with self._session_lock:
            for session_id, session in self._sessions.items():
                if session.process.poll() is not None:
                    to_remove.append((session_id, session))

        # Stop reading and join threads outside the lock to avoid blocking
        for session_id, session in to_remove:
            session.stop_reading.set()
            for t in session.read_threads:
                if t.is_alive():
                    t.join(timeout=1.0)

        with self._session_lock:
            for session_id, _ in to_remove:
                self._sessions.pop(session_id, None)
                logger.info(
                    "[InteractiveShell] Cleaned up terminated session: %s", session_id
                )

    def _cleanup_idle_sessions(self) -> None:
        """Terminate sessions that have been idle for too long."""
        now = time.time()
        to_remove: list[tuple[str, _LocalInteractiveSession]] = []
        with self._session_lock:
            for session_id, session in self._sessions.items():
                if session.process.poll() is None:  # Still running
                    idle_time = now - session.last_activity
                    if idle_time > self._session_timeout_seconds:
                        to_remove.append((session_id, session))

        for session_id, session in to_remove:
            logger.warning(
                "[InteractiveShell] Session %s idle for %.0fs, forcing termination",
                session_id,
                self._session_timeout_seconds,
            )
            session.stop_reading.set()
            try:
                session.process.kill()
                session.process.wait(timeout=2.0)
            except Exception:
                pass
            for t in session.read_threads:
                if t.is_alive():
                    t.join(timeout=1.0)

        with self._session_lock:
            for session_id, _ in to_remove:
                self._sessions.pop(session_id, None)

    def _start_reader_threads(self, session: _LocalInteractiveSession) -> None:
        """Start background threads to read process output (binary mode)."""

        def _read_stream(stream, is_stderr: bool) -> None:
            """Continuously read from a stream into the buffer."""
            try:
                while not session.stop_reading.is_set():
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    with session.lock:
                        if is_stderr:
                            session.stderr_buffer.extend(chunk)
                        else:
                            session.stdout_buffer.extend(chunk)
                        session.last_activity = time.time()
            except Exception:
                pass

        if session.process.stdout:
            t = threading.Thread(
                target=_read_stream,
                args=(session.process.stdout, False),
                daemon=True,
            )
            t.start()
            session.read_threads.append(t)

        if session.process.stderr:
            t = threading.Thread(
                target=_read_stream,
                args=(session.process.stderr, True),
                daemon=True,
            )
            t.start()
            session.read_threads.append(t)

    async def start(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool = True,
    ) -> InteractiveSession:
        """Start an interactive shell session."""
        await self._ensure_cleanup_task()

        def _start() -> _LocalInteractiveSession:
            with self._session_lock:
                if len(self._sessions) >= self._max_sessions:
                    raise RuntimeError(
                        f"Maximum number of interactive sessions ({self._max_sessions}) reached. "
                        f"Please stop some sessions before starting new ones."
                    )

            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})
            working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()

            # Ensure UTF-8 mode on Windows for proper Unicode support
            if sys.platform == "win32":
                run_env["PYTHONIOENCODING"] = "utf-8"

            # Use binary mode for reliable cross-platform pipe behavior
            popen_kwargs: dict[str, Any] = {
                "shell": shell,
                "cwd": working_dir,
                "env": run_env,
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                # Binary mode - we decode manually
                "bufsize": 0,  # Unbuffered for immediate reading
            }

            actual_command = command
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                # For cmd.exe on Windows, prefix with chcp to set UTF-8 code page
                if shell and actual_command.strip().lower().startswith("cmd"):
                    actual_command = f"chcp 65001 >nul && {actual_command}"

            proc = subprocess.Popen(actual_command, **popen_kwargs)

            session_id = str(uuid.uuid4())[:8]
            session = _LocalInteractiveSession(
                session_id=session_id,
                command=command,
                process=proc,
            )
            self._start_reader_threads(session)
            return session

        session = await asyncio.to_thread(_start)

        with self._session_lock:
            self._sessions[session.session_id] = session

        logger.info(
            "[InteractiveShell] Started session %s (pid=%d): %s",
            session.session_id,
            session.process.pid,
            command,
        )

        # Wait for process to initialize
        await asyncio.sleep(0.3)

        return InteractiveSession(
            session_id=session.session_id,
            command=command,
            pid=session.process.pid,
            state=InteractiveSessionState.RUNNING,
            created_at=session.created_at,
            last_activity=session.last_activity,
        )

    async def send(
        self,
        session_id: str,
        input_data: str,
        send_eof: bool = False,
    ) -> None:
        """Send input to an interactive session."""

        def _send() -> None:
            session = self._get_session(session_id)
            if session.process.stdin is None:
                raise RuntimeError("Session stdin is not available")
            if session.process.poll() is not None:
                raise RuntimeError("Session process has already exited")

            # Encode to bytes for binary-mode pipe
            data = input_data.encode("utf-8", errors="replace")
            if not input_data.endswith("\n"):
                data += b"\n"

            session.process.stdin.write(data)
            session.process.stdin.flush()
            session.last_activity = time.time()

            if send_eof:
                session.process.stdin.close()

        await asyncio.to_thread(_send)

    async def read(
        self,
        session_id: str,
        timeout: float = 5.0,
        max_chars: int | None = None,
    ) -> str:
        """Read output from an interactive session."""

        def _read() -> str:
            session = self._get_session(session_id)
            deadline = time.time() + timeout
            result_parts: list[str] = []
            chars_collected = 0
            has_data = False

            while time.time() < deadline:
                stdout_chunk = b""
                stderr_chunk = b""

                with session.lock:
                    if session.stdout_buffer:
                        stdout_chunk = bytes(session.stdout_buffer)
                        session.stdout_buffer.clear()
                    if session.stderr_buffer:
                        stderr_chunk = bytes(session.stderr_buffer)
                        session.stderr_buffer.clear()

                # Decode chunks
                chunks = [(stdout_chunk, False), (stderr_chunk, True)]
                for chunk, is_stderr in chunks:
                    if not chunk:
                        continue

                    try:
                        text = chunk.decode("utf-8", errors="replace")
                    except Exception:
                        text = chunk.decode("utf-8", errors="replace")

                    # On Windows, also try system encoding if UTF-8 produces all replacement chars
                    if sys.platform == "win32" and "\ufffd" in text and len(text) > 1:
                        # All chars became replacement characters - try system code page
                        for fallback_encoding in ("gbk", "gb18030", "cp936"):
                            try:
                                fallback_text = chunk.decode(fallback_encoding)
                                if "\ufffd" not in fallback_text:
                                    text = fallback_text
                                    break
                            except (UnicodeDecodeError, LookupError):
                                continue

                    if max_chars and chars_collected + len(text) > max_chars:
                        take = max_chars - chars_collected
                        result_parts.append(text[:take])
                        # Put back overflow
                        overflow = text[take:].encode("utf-8", errors="replace")
                        with session.lock:
                            if is_stderr:
                                session.stderr_buffer[:0] = overflow
                            else:
                                session.stdout_buffer[:0] = overflow
                        chars_collected += take
                        has_data = True
                        break

                    result_parts.append(text)
                    chars_collected += len(text)
                    has_data = True

                if has_data:
                    # Give a small grace period for more rapid output
                    grace_end = time.time() + 0.15
                    while time.time() < grace_end:
                        with session.lock:
                            if session.stdout_buffer or session.stderr_buffer:
                                break
                        time.sleep(0.03)
                    if time.time() >= grace_end:
                        break
                    continue

                # No data yet, wait
                time.sleep(0.05)

            return "".join(result_parts)

        return await asyncio.to_thread(_read)

    async def interact(
        self,
        session_id: str,
        input_data: str,
        timeout: float = 5.0,
        max_chars: int | None = None,
    ) -> str:
        """Send input and read output atomically."""
        await self.send(session_id, input_data)
        # Allow process time to react
        await asyncio.sleep(0.1)
        return await self.read(session_id, timeout=timeout, max_chars=max_chars)

    async def terminate(
        self,
        session_id: str,
        graceful: bool = True,
    ) -> InteractiveSession:
        """Terminate an interactive session."""

        def _terminate() -> InteractiveSession:
            session = self._get_session(session_id)
            proc = session.process

            session.stop_reading.set()

            if proc.poll() is not None:
                exit_code = proc.returncode
            else:
                if graceful:
                    if sys.platform == "win32":
                        try:
                            proc.send_signal(subprocess.signal.CTRL_C_EVENT)
                        except (ValueError, OSError):
                            pass
                    else:
                        try:
                            proc.send_signal(subprocess.signal.SIGINT)
                        except (ValueError, OSError):
                            pass

                    try:
                        exit_code = proc.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        exit_code = None
                else:
                    exit_code = None

                if proc.poll() is None:
                    proc.kill()
                    try:
                        exit_code = proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        exit_code = None
                    # Force-set exit code if process is still alive after kill
                    if proc.poll() is None:
                        exit_code = -9

            for pipe in [proc.stdin, proc.stdout, proc.stderr]:
                if pipe:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            for t in session.read_threads:
                if t.is_alive():
                    t.join(timeout=1.0)

            with self._session_lock:
                self._sessions.pop(session_id, None)

            logger.info(
                "[InteractiveShell] Terminated session %s (exit_code=%s)",
                session_id,
                exit_code,
            )

            return InteractiveSession(
                session_id=session_id,
                command=session.command,
                pid=proc.pid,
                state=InteractiveSessionState.TERMINATED,
                exit_code=exit_code,
                created_at=session.created_at,
                last_activity=session.last_activity,
            )

        return await asyncio.to_thread(_terminate)

    async def get_session(self, session_id: str) -> InteractiveSession | None:
        """Get information about a session."""

        def _get() -> InteractiveSession | None:
            with self._session_lock:
                session = self._sessions.get(session_id)
                if session is None:
                    return None

                proc = session.process
                poll_result = proc.poll()
                if poll_result is not None:
                    state = InteractiveSessionState.TERMINATED
                    exit_code = poll_result
                else:
                    state = InteractiveSessionState.RUNNING
                    exit_code = None

                return InteractiveSession(
                    session_id=session_id,
                    command=session.command,
                    pid=proc.pid,
                    state=state,
                    exit_code=exit_code,
                    created_at=session.created_at,
                    last_activity=session.last_activity,
                )

        return await asyncio.to_thread(_get)

    async def list_sessions(self) -> list[InteractiveSession]:
        """List all active interactive sessions."""

        def _list() -> list[InteractiveSession]:
            result = []
            with self._session_lock:
                for session_id, session in self._sessions.items():
                    proc = session.process
                    poll_result = proc.poll()
                    if poll_result is not None:
                        state = InteractiveSessionState.TERMINATED
                        exit_code = poll_result
                    else:
                        state = InteractiveSessionState.RUNNING
                        exit_code = None

                    result.append(
                        InteractiveSession(
                            session_id=session_id,
                            command=session.command,
                            pid=proc.pid,
                            state=state,
                            exit_code=exit_code,
                            created_at=session.created_at,
                            last_activity=session.last_activity,
                        )
                    )
            return result

        return await asyncio.to_thread(_list)

    def _get_session(self, session_id: str) -> _LocalInteractiveSession:
        """Get internal session by ID (synchronous, must be called from thread)."""
        with self._session_lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Interactive session not found: {session_id}")
        return session
