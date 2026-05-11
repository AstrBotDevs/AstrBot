"""Persistent bash session for stateful shell execution.

Each session wraps a single long-running bash process. Commands are sent via
stdin and output is delimited by unique exit-code markers for reliable parsing.
Because it is the same process, ``cd`` / ``export`` / ``source`` etc. persist
naturally across tool calls within a session (UMO).
"""

from __future__ import annotations

import asyncio
import shlex
import uuid
from typing import Any


class PersistentShellSession:
    """A single long-running bash process with stateful ``exec()``.

    The session is identified by a string key (typically the UMO).  Only one
    command runs at a time (serialised via an internal lock).
    """

    _instances: dict[str, PersistentShellSession] = {}

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._marker = uuid.uuid4().hex[:6]
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Process lifecycle
    # ------------------------------------------------------------------

    async def _ensure_running(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            "bash",
            "--norc",
            "--noprofile",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

    async def shutdown(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        stdin = proc.stdin
        if stdin is not None:
            try:
                stdin.write(b"exit\n")
                await stdin.drain()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (TimeoutError, asyncio.TimeoutError):
                proc.kill()
                await proc.wait()

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 30,
        background: bool = False,
    ) -> dict[str, Any]:
        """Execute *command* inside the persistent bash session.

        Parameters
        ----------
        command : str
            Shell command to run.
        cwd : str | None
            If given, change to this directory **for this command only**
            (via ``cd {cwd} && …``).  *Omit* to let the session keep whatever
            working directory it is currently in.
        env : dict[str, str] | None
            Extra environment variables for **this command only**.
        timeout : int | None
            Maximum seconds to wait for the command to finish.
        background : bool
            If True, the command is launched via ``nohup`` in the background
            and the call returns immediately.

        Returns
        -------
        dict with keys ``stdout``, ``stderr``, ``exit_code`` and (when
        background) ``background_task``.
        """
        await self._ensure_running()

        if background:
            return await self._exec_background(command, cwd, env)

        async with self._lock:
            return await self._exec_foreground(command, cwd, env, timeout)

    async def _exec_foreground(
        self,
        command: str,
        cwd: str | None,
        env: dict[str, str] | None,
        timeout: int | None,
    ) -> dict[str, Any]:
        proc = self._proc
        assert proc is not None
        stdin = proc.stdin
        assert stdin is not None
        prefix = self._build_prefix(cwd, env)
        sentinel = f"{self._marker}_EXIT"
        line = f'{prefix}{{ {command}; }} 2>&1\necho "{sentinel}:$?"\n'

        stdin.write(line.encode())
        await stdin.drain()

        buf = await self._read_until(f"{sentinel}:".encode(), timeout)

        text = buf.decode("utf-8", errors="replace")
        exit_code = 0
        clean: list[str] = []
        for ln in text.splitlines():
            if f"{sentinel}:" in ln:
                try:
                    exit_code = int(ln.split(":", 1)[1])
                except (ValueError, IndexError):
                    exit_code = -1
            else:
                clean.append(ln)

        return {
            "stdout": "\n".join(clean).strip(),
            "stderr": "",
            "exit_code": exit_code,
        }

    async def _exec_background(
        self,
        command: str,
        cwd: str | None,
        env: dict[str, str] | None,
    ) -> dict[str, Any]:
        proc = self._proc
        assert proc is not None
        stdin = proc.stdin
        assert stdin is not None
        prefix = self._build_prefix(cwd, env)
        job_id = uuid.uuid4().hex[:8]
        out_file = f"/tmp/astrbot_bg_{job_id}.out"

        bg_line = (
            f"{prefix}nohup bash -c {shlex.quote(command)} "
            f"> {shlex.quote(out_file)} 2>&1 &\n"
            f'echo "BG_PID=$!"\n'
        )
        stdin.write(bg_line.encode())
        await stdin.drain()

        pid_buf = await self._read_until(b"BG_PID=", timeout=5)
        pid: str | None = None
        for ln in pid_buf.decode(errors="replace").splitlines():
            if "BG_PID=" in ln:
                pid = ln.split("=", 1)[1].strip()

        return {
            "stdout": (
                f"Background task started.\n"
                f"  job_id:  {job_id}\n"
                f"  pid:     {pid}\n"
                f"  command: {command}\n"
                f"  output:  {out_file}\n"
            ),
            "stderr": "",
            "exit_code": None,
            "background_task": {
                "job_id": job_id,
                "pid": pid,
                "out_file": out_file,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prefix(cwd: str | None, env: dict[str, str] | None) -> str:
        parts: list[str] = []
        if env:
            for k, v in env.items():
                parts.append(f"export {shlex.quote(str(k))}={shlex.quote(str(v))}; ")
        if cwd:
            parts.append(f"cd {shlex.quote(cwd)} && ")
        return "".join(parts)

    async def _read_until(self, end_marker: bytes, timeout: float | None) -> bytes:
        assert self._proc is not None
        stdout = self._proc.stdout
        assert stdout is not None
        buf = b""
        deadline = (
            None if timeout is None else asyncio.get_event_loop().time() + timeout
        )
        while True:
            remaining = timeout
            if deadline is not None:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
            try:
                chunk = await asyncio.wait_for(
                    stdout.read(4096),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf += chunk
            if end_marker in buf:
                break
        return buf

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def get_or_create(cls, key: str) -> PersistentShellSession:
        """Return (or create and return) the session for *key*."""
        if key not in cls._instances:
            cls._instances[key] = cls()
        return cls._instances[key]

    @classmethod
    async def cleanup(cls, key: str) -> None:
        """Shut down and remove the session for *key*."""
        if key in cls._instances:
            await cls._instances[key].shutdown()
            del cls._instances[key]

    @classmethod
    async def cleanup_all(cls) -> None:
        """Shut down **all** sessions (called on application shutdown)."""
        for key in list(cls._instances):
            await cls.cleanup(key)
