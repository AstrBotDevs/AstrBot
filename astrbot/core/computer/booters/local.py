from __future__ import annotations

import asyncio
import locale
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
from astrbot.core.computer.olayer import (
    FileSystemComponent,
    PythonComponent,
    ShellComponent,
)
from astrbot.core.computer.shell_session import PersistentShellSession
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_root,
    get_astrbot_temp_path,
    get_astrbot_workspaces_path,
)

from .base import ComputerBooter
from .bwrap import _decode_shell_output

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


def _ensure_safe_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    allowed_roots = [
        os.path.abspath(get_astrbot_root()),
        os.path.abspath(get_astrbot_data_path()),
        os.path.abspath(get_astrbot_temp_path()),
        os.path.abspath(get_astrbot_workspaces_path()),
    ]
    if not any(abs_path.startswith(root) for root in allowed_roots):
        raise PermissionError("Path is outside the allowed computer roots.")
    return abs_path


def _decode_bytes_with_fallback(
    output: bytes | None,
    *,
    preferred_encoding: str | None = None,
) -> str:
    if output is None:
        return ""


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

@dataclass
class LocalShellComponent(ShellComponent):
    policy: LocalSandboxPolicy

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,
        shell: bool = True,
        background: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")

        key = session_id or "default"
        session = PersistentShellSession.get_or_create(key)
        return await session.exec(
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            background=background,
        )

    @staticmethod
    async def shutdown_all() -> None:
        await PersistentShellSession.cleanup_all()


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
                # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                # Executes the current interpreter with a fixed argv list and shell=False.
                result = subprocess.run(
                    [os.environ.get("PYTHON", sys.executable), "-c", code],
                    check=False,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                    shell=False,
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
                    },
                }
            except subprocess.TimeoutExpired:
                return {
                    "data": {
                        "output": {"text": "", "images": []},
                        "error": "Execution timed out.",
                    },
                }

        return await asyncio.to_thread(_run)


@dataclass
class LocalFileSystemComponent(FileSystemComponent):
    policy: LocalSandboxPolicy

    async def create_file(
        self,
        path: str,
        content: str = "",
        mode: int = 0o644,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            abs_path.chmod(mode)
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path)
            with open(abs_path, "rb") as f:
                raw_content = f.read()
            content = _decode_bytes_with_fallback(
                raw_content,
                preferred_encoding=encoding,
            )
            if offset is not None:
                lines = content.splitlines(keepends=True)
                start = offset
                if limit is not None:
                    lines = lines[start : start + limit]
                else:
                    lines = lines[start:]
                content = "".join(lines)
            elif limit is not None:
                lines = content.splitlines(keepends=True)[:limit]
                content = "".join(lines)
            return {"success": True, "content": content}

        return await asyncio.to_thread(_run)

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict[str, Any]:
        """Search file contents using grep-like pattern matching."""

        def _run() -> dict[str, Any]:
            search_path = _ensure_safe_path(path) if path else "."
            cmd = ["grep", "-rn", pattern, search_path]
            if after_context is not None:
                cmd.extend(["-A", str(after_context)])
            if before_context is not None:
                cmd.extend(["-B", str(before_context)])
            if glob:
                cmd.extend(["--include", glob])
            try:
                result = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return {
                    "success": True,
                    "content": result.stdout,
                    "error": result.stderr if result.returncode != 0 else "",
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "output": "",
                    "error": "Search timed out.",
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
            abs_path = _ensure_safe_path(path)
            with open(abs_path, encoding=encoding) as f:
                content = f.read()
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
            if new_content == content:
                return {
                    "success": False,
                    "error": f"String '{old_string}' not found in file.",
                }
            with open(abs_path, "w", encoding=encoding) as f:
                f.write(new_content)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "w",
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, mode, encoding=encoding) as f:
                f.write(content)
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def delete_file(self, path: str) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path)
            if os.path.isdir(abs_path):
                shutil.rmtree(abs_path)
            else:
                abs_path.unlink()
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def list_dir(
        self,
        path: str = ".",
        show_hidden: bool = False,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path)
            entries = os.listdir(abs_path)
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

    async def shutdown(self, **kwargs) -> None:
        await LocalShellComponent.shutdown_all()
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
            "LocalBooter does not support upload_file operation. Use shell instead.",
        )

    async def download_file(self, remote_path: str, local_path: str) -> None:
        raise NotImplementedError(
            "LocalBooter does not support download_file operation. Use shell instead.",
        )

    async def available(self) -> bool:
        return True
