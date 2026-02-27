from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_root

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter

SandboxBackend = Literal["none", "bwrap", "seatbelt"]

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


def _is_safe_command(command: str) -> bool:
    cmd = f" {command.strip().lower()} "
    return not any(pat in cmd for pat in _BLOCKED_COMMAND_PATTERNS)


def _escape_seatbelt_string(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace('"', '\\"')


def _session_workspace_name(session_id: str) -> str:
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id).strip("._-")
    if not safe_prefix:
        safe_prefix = "session"
    safe_prefix = safe_prefix[:40]
    suffix = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex[:12]
    return f"{safe_prefix}_{suffix}"


def _detect_sandbox_backend() -> SandboxBackend:
    if sys.platform.startswith("linux"):
        if shutil.which("bwrap"):
            return "bwrap"
        raise RuntimeError("Local runtime requires 'bwrap' on Linux.")

    if sys.platform == "darwin":
        if shutil.which("sandbox-exec"):
            return "seatbelt"
        raise RuntimeError("Local runtime requires 'sandbox-exec' on macOS.")

    return "none"


@dataclass(frozen=True)
class LocalSandboxPolicy:
    workspace: Path
    backend: SandboxBackend
    sandboxed: bool
    default_cwd: Path

    @classmethod
    def build_default(cls, session_id: str, sandboxed: bool) -> LocalSandboxPolicy:
        workspace_root_raw = os.environ.get(
            "ASTRBOT_LOCAL_WORKSPACE_ROOT"
        ) or os.environ.get("ASTRBOT_LOCAL_WORKSPACE", "~/.astrbot/workspace")
        workspace_root = Path(workspace_root_raw).expanduser().resolve()
        workspace = workspace_root / _session_workspace_name(session_id)
        default_cwd = workspace if sandboxed else Path(get_astrbot_root()).resolve()
        return cls(
            workspace=workspace,
            backend=_detect_sandbox_backend() if sandboxed else "none",
            sandboxed=sandboxed,
            default_cwd=default_cwd,
        )

    def ensure_workspace(self) -> None:
        try:
            self.workspace.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise RuntimeError(
                "Cannot create local workspace. "
                "Set ASTRBOT_LOCAL_WORKSPACE_ROOT to a writable path."
            ) from exc

    def resolve_path(self, path: str, base: Path | None = None) -> Path:
        raw = Path(path).expanduser()
        resolved = raw if raw.is_absolute() else (base or self.default_cwd) / raw
        return resolved.resolve()

    def ensure_writable_path(self, path: str) -> Path:
        abs_path = self.resolve_path(path)
        if self.sandboxed and not abs_path.is_relative_to(self.workspace):
            raise PermissionError(
                f"Write path is outside workspace: {self.workspace.as_posix()}"
            )
        return abs_path

    def normalize_working_dir(self, cwd: str | None) -> Path:
        target = self.resolve_path(cwd) if cwd else self.default_cwd
        if not target.exists():
            raise FileNotFoundError(f"Working directory does not exist: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Working directory is not a directory: {target}")
        return target

    def wrap_command(self, command: list[str], working_dir: Path) -> list[str]:
        if not self.sandboxed:
            return command

        if self.backend == "bwrap":
            return [
                "bwrap",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/",
                "/",
                "--bind",
                str(self.workspace),
                str(self.workspace),
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--chdir",
                str(working_dir),
                "--",
                *command,
            ]

        if self.backend == "seatbelt":
            workspace_escaped = _escape_seatbelt_string(str(self.workspace))
            profile = "\n".join(
                [
                    "(version 1)",
                    "(deny default)",
                    '(import "system.sb")',
                    "(allow process*)",
                    "(allow file-read*)",
                    f'(allow file-write* (subpath "{workspace_escaped}"))',
                    "(allow network*)",
                ]
            )
            return ["sandbox-exec", "-p", profile, *command]

        raise RuntimeError("Sandbox backend is not available for local_sandboxed mode.")


@dataclass
class LocalShellComponent(ShellComponent):
    policy: LocalSandboxPolicy

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 30,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")

        def _run() -> dict[str, Any]:
            shell_command = (
                ["/bin/sh", "-lc", command] if shell else shlex.split(command)
            )
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})

            working_dir = self.policy.normalize_working_dir(cwd)
            wrapped_command = self.policy.wrap_command(shell_command, working_dir)
            if background:
                proc = subprocess.Popen(
                    wrapped_command,
                    shell=False,
                    cwd=working_dir,
                    env=run_env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}
            try:
                result = subprocess.run(
                    wrapped_command,
                    shell=False,
                    cwd=working_dir,
                    env=run_env,
                    timeout=timeout,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                }
            except subprocess.TimeoutExpired:
                timeout_seconds = timeout if timeout is not None else "configured"
                return {
                    "stdout": "",
                    "stderr": f"Execution timed out after {timeout_seconds} seconds.",
                    "exit_code": 124,
                }

        return await asyncio.to_thread(_run)


@dataclass
class LocalPythonComponent(PythonComponent):
    policy: LocalSandboxPolicy

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            python_command = [os.environ.get("PYTHON", sys.executable), "-c", code]
            working_dir = self.policy.normalize_working_dir(None)
            wrapped_command = self.policy.wrap_command(python_command, working_dir)
            try:
                result = subprocess.run(
                    wrapped_command,
                    cwd=working_dir,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                )
                stdout = "" if silent else result.stdout
                stderr = result.stderr if result.returncode != 0 else ""
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
    policy: LocalSandboxPolicy

    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.ensure_writable_path(path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            with abs_path.open("w", encoding="utf-8") as f:
                f.write(content)
            abs_path.chmod(mode)
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def read_file(self, path: str, encoding: str = "utf-8") -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.resolve_path(path)
            with abs_path.open(encoding=encoding) as f:
                content = f.read()
            return {"success": True, "content": content}

        return await asyncio.to_thread(_run)

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.ensure_writable_path(path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            with abs_path.open(mode, encoding=encoding) as f:
                f.write(content)
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def delete_file(self, path: str) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.ensure_writable_path(path)
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
            else:
                abs_path.unlink()
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.resolve_path(path)
            entries = [entry.name for entry in abs_path.iterdir()]
            if not show_hidden:
                entries = [e for e in entries if not e.startswith(".")]
            return {"success": True, "entries": entries}

        return await asyncio.to_thread(_run)


class LocalBooter(ComputerBooter):
    def __init__(self, session_id: str, sandboxed: bool = False) -> None:
        self._session_id = session_id
        self._policy = LocalSandboxPolicy.build_default(
            session_id=session_id, sandboxed=sandboxed
        )
        if sandboxed:
            self._policy.ensure_workspace()
        if sandboxed and self._policy.backend == "none":
            logger.warning(
                f"Local runtime sandbox backend is unavailable on {sys.platform}. "
                "Only filesystem tools are restricted to workspace."
            )
        self._fs = LocalFileSystemComponent(policy=self._policy)
        self._python = LocalPythonComponent(policy=self._policy)
        self._shell = LocalShellComponent(policy=self._policy)

    async def boot(self, session_id: str) -> None:
        logger.info(
            f"Local computer booter initialized for session: {session_id} "
            f"(sandboxed={self._policy.sandboxed}, "
            f"backend={self._policy.backend}, workspace={self._policy.workspace})"
        )

    async def shutdown(self) -> None:
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
