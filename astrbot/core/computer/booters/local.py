from __future__ import annotations

import asyncio
import locale
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from astrbot.api import logger
from astrbot.core.computer.shell_session import PersistentShellSession
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_root,
    get_astrbot_temp_path,
    get_astrbot_workspaces_path,
)

from ..olayer import (
    FileSystemComponent,
    InteractiveShellComponent,
    PythonComponent,
    ShellComponent,
)
from .base import ComputerBooter
from .local_interactive_shell import LocalInteractiveShellComponent

SandboxBackend = Literal["none", "bwrap", "seatbelt"]
_MAX_LINE_LENGTH = 2000


def _truncate_long_lines(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        if len(body) > _MAX_LINE_LENGTH:
            body = f"{body[:_MAX_LINE_LENGTH]}...[truncated]"
        lines.append(body + newline)
    return "".join(lines)


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


def _decode_process_output(
    output: bytes | None,
    *,
    normalize_newlines: bool = False,
) -> str:
    decoded = _decode_bytes_with_fallback(output, preferred_encoding="utf-8")
    if normalize_newlines:
        decoded = decoded.replace("\r\n", "\n")
    return decoded


def _is_windows_shell() -> bool:
    return os.name == "nt"


def _merged_env(env: dict[str, str] | None) -> dict[str, str] | None:
    if not env:
        return None
    merged = os.environ.copy()
    merged.update(env)
    return merged


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
    def build_default(
        cls,
        session_id: str = "default",
        sandboxed: bool = False,
    ) -> LocalSandboxPolicy:
        workspace_root_raw = os.environ.get(
            "ASTRBOT_LOCAL_WORKSPACE_ROOT",
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
                "Set ASTRBOT_LOCAL_WORKSPACE_ROOT to a writable path.",
            ) from exc

    def resolve_path(self, path: str, base: Path | None = None) -> Path:
        raw = Path(path).expanduser()
        resolved = raw if raw.is_absolute() else (base or self.default_cwd) / raw
        return resolved.resolve()

    def ensure_writable_path(self, path: str) -> Path:
        abs_path = self.resolve_path(path)
        if self.sandboxed and not abs_path.is_relative_to(self.workspace):
            raise PermissionError(
                f"Write path is outside workspace: {self.workspace.as_posix()}",
            )
        return abs_path

    def normalize_working_dir(self, cwd: str | None) -> Path:
        target = self.resolve_path(cwd) if cwd else self.default_cwd
        if not target.exists():
            raise FileNotFoundError(f"Working directory does not exist: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Working directory is not a directory: {target}")
        return target

    def wrap_command(self, command: list[str], _working_dir: Path) -> list[str]:
        return command


def _default_policy() -> LocalSandboxPolicy:
    return LocalSandboxPolicy.build_default()


@dataclass
class LocalShellComponent(ShellComponent):
    policy: LocalSandboxPolicy = field(default_factory=_default_policy)

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

        if _is_windows_shell():
            return await self._exec_windows_command(
                command=command,
                cwd=cwd,
                env=env,
                timeout=timeout,
                background=background,
            )

        key = session_id or "default"
        session = PersistentShellSession.get_or_create(key)
        return await session.exec(
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            background=background,
        )

    async def _exec_windows_command(
        self,
        *,
        command: str,
        cwd: str | None,
        env: dict[str, str] | None,
        timeout: int | None,
        background: bool,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            working_dir = str(self.policy.normalize_working_dir(cwd)) if cwd else None
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            if background:
                job_id = uuid.uuid4().hex[:8]
                out_file = Path(get_astrbot_temp_path()) / f"astrbot_bg_{job_id}.out"
                out_file.parent.mkdir(parents=True, exist_ok=True)
                output = open(out_file, "ab")
                try:
                    proc = subprocess.Popen(
                        command,
                        cwd=working_dir,
                        env=_merged_env(env),
                        shell=True,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        creationflags=creation_flags,
                    )
                finally:
                    output.close()

                return {
                    "stdout": (
                        f"Background task started.\n"
                        f"  job_id:  {job_id}\n"
                        f"  pid:     {proc.pid}\n"
                        f"  command: {command}\n"
                        f"  output:  {out_file}\n"
                    ),
                    "stderr": "",
                    "exit_code": None,
                    "background_task": {
                        "job_id": job_id,
                        "pid": proc.pid,
                        "out_file": str(out_file),
                    },
                }

            try:
                result = subprocess.run(
                    command,
                    cwd=working_dir,
                    env=_merged_env(env),
                    shell=True,
                    check=False,
                    timeout=timeout,
                    capture_output=True,
                    text=False,
                    creationflags=creation_flags,
                )
                return {
                    "stdout": _decode_process_output(
                        result.stdout,
                        normalize_newlines=True,
                    ).strip(),
                    "stderr": _decode_process_output(
                        result.stderr,
                        normalize_newlines=True,
                    ).strip(),
                    "exit_code": result.returncode,
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "stdout": _decode_process_output(
                        exc.stdout,
                        normalize_newlines=True,
                    ).strip(),
                    "stderr": "Execution timed out.",
                    "exit_code": -1,
                }

        return await asyncio.to_thread(_run)

    @staticmethod
    async def shutdown_all() -> None:
        await PersistentShellSession.cleanup_all()


@dataclass
class LocalPythonComponent(PythonComponent):
    policy: LocalSandboxPolicy = field(default_factory=_default_policy)

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            python_command = [sys.executable, "-c", code]
            working_dir = self.policy.normalize_working_dir(None)
            wrapped_command = self.policy.wrap_command(python_command, working_dir)
            try:
                result = subprocess.run(
                    wrapped_command,
                    check=False,
                    timeout=timeout,
                    capture_output=True,
                    text=False,
                    shell=False,
                )
                stdout = (
                    ""
                    if silent
                    else _decode_process_output(
                        result.stdout,
                        normalize_newlines=True,
                    )
                )
                stderr = _decode_process_output(
                    result.stderr,
                    normalize_newlines=True,
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
    policy: LocalSandboxPolicy = field(default_factory=_default_policy)

    async def create_file(
        self,
        path: str,
        content: str = "",
        mode: int = 0o644,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.ensure_writable_path(_ensure_safe_path(path))
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
            os.chmod(abs_path, mode)
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
            ).replace("\r\n", "\n")
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
        def _run() -> dict[str, Any]:
            search_path = _ensure_safe_path(path) if path else "."
            if os.name == "nt":
                matches: list[str] = []
                root = Path(search_path)
                files = [root] if root.is_file() else root.rglob(glob or "*")
                for candidate in files:
                    if not candidate.is_file():
                        continue
                    try:
                        text = candidate.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        text = _decode_bytes_with_fallback(candidate.read_bytes())
                    except OSError:
                        continue
                    for line_number, line in enumerate(text.splitlines(), start=1):
                        if pattern in line:
                            matches.append(f"{candidate}:{line_number}:{line}\n")
                return {
                    "success": True,
                    "content": _truncate_long_lines("".join(matches)),
                    "error": "",
                }

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
                    "content": _truncate_long_lines(result.stdout),
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
            abs_path = self.policy.ensure_writable_path(_ensure_safe_path(path))
            content = abs_path.read_text(encoding=encoding)
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
            abs_path.write_text(updated, encoding=encoding)
            return {
                "success": True,
                "path": str(abs_path),
                "replacements": replacements,
            }

        return await asyncio.to_thread(_run)

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "w",
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.ensure_writable_path(_ensure_safe_path(path))
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(abs_path, mode, encoding=encoding) as f:
                f.write(content)
            return {"success": True, "path": str(abs_path)}

        return await asyncio.to_thread(_run)

    async def delete_file(self, path: str) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = self.policy.ensure_writable_path(_ensure_safe_path(path))
            if abs_path.is_dir():
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
    def __init__(self, session_id: str = "default", sandboxed: bool = False) -> None:
        self._session_id = session_id
        self._policy = LocalSandboxPolicy.build_default(
            session_id=session_id,
            sandboxed=sandboxed,
        )
        if sandboxed:
            self._policy.ensure_workspace()
        if sandboxed and self._policy.backend == "none":
            logger.warning(
                f"Local runtime sandbox backend is unavailable on {sys.platform}. "
                "Only filesystem tools are restricted to workspace.",
            )
        self._fs = LocalFileSystemComponent(policy=self._policy)
        self._python = LocalPythonComponent(policy=self._policy)
        self._shell = LocalShellComponent(policy=self._policy)
        self._interactive_shell = LocalInteractiveShellComponent()

    async def boot(self, session_id: str) -> None:
        logger.info(
            f"Local computer booter initialized for session: {session_id} "
            f"(sandboxed={self._policy.sandboxed}, "
            f"backend={self._policy.backend}, workspace={self._policy.workspace})",
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

    @property
    def interactive_shell(self) -> InteractiveShellComponent:
        return self._interactive_shell

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
