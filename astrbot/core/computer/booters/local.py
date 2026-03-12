from __future__ import annotations

import asyncio
import locale
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_root,
    get_astrbot_temp_path,
)

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter

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


def _is_path_under_root(abs_path: str, root: str) -> bool:
    """Check if abs_path is under the given root directory using commonpath.

    This avoids the prefix-matching issue with startswith (e.g., /data matching /data2).
    """
    try:
        return os.path.commonpath([abs_path, root]) == root
    except ValueError:
        # Different drives on Windows
        return False


def _ensure_safe_path(path: str, extra_allowed_roots: Iterable[str] = ()) -> str:
    abs_path = os.path.abspath(path)
    allowed_roots = [
        os.path.abspath(get_astrbot_root()),
        os.path.abspath(get_astrbot_data_path()),
        os.path.abspath(get_astrbot_temp_path()),
    ]
    allowed_roots.extend(os.path.abspath(r) for r in extra_allowed_roots if r)

    if not any(_is_path_under_root(abs_path, root) for root in allowed_roots):
        raise PermissionError("Path is outside the allowed computer roots.")
    return abs_path


def _resolve_work_dir(
    cwd: str | None,
    configured_work_dir: str | None,
    extra_allowed_roots: Iterable[str] = (),
) -> str:
    """Resolve the working directory with consistent priority rules.

    Priority:
    1. User-supplied cwd (requires safety check)
    2. Configured work_dir
    3. Default AstrBot root directory
    """
    if cwd:
        return _ensure_safe_path(cwd, extra_allowed_roots)
    return configured_work_dir or get_astrbot_root()


def _decode_shell_output(output: bytes | None) -> str:
    if output is None:
        return ""

    preferred = locale.getpreferredencoding(False) or "utf-8"
    try:
        return output.decode("utf-8")
    except (LookupError, UnicodeDecodeError):
        pass

    if os.name == "nt":
        for encoding in ("mbcs", "cp936", "gbk", "gb18030"):
            try:
                return output.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue

    try:
        return output.decode(preferred)
    except (LookupError, UnicodeDecodeError):
        pass

    return output.decode("utf-8", errors="replace")


@dataclass
class LocalShellComponent(ShellComponent):
    _work_dir: str = field(default="", repr=False)
    _extra_allowed_roots: list[str] = field(default_factory=list, repr=False)

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
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})
            working_dir = _resolve_work_dir(
                cwd=cwd,
                configured_work_dir=self._work_dir,
                extra_allowed_roots=self._extra_allowed_roots,
            )
            if background:
                # `command` is intentionally executed through the current shell so
                # local computer-use behavior matches existing tool semantics.
                # Safety relies on `_is_safe_command()` and the allowed-root checks.
                proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    command,
                    shell=shell,
                    cwd=working_dir,
                    env=run_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}
            # `command` is intentionally executed through the current shell so
            # local computer-use behavior matches existing tool semantics.
            # Safety relies on `_is_safe_command()` and the allowed-root checks.
            result = subprocess.run(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                command,
                shell=shell,
                cwd=working_dir,
                env=run_env,
                timeout=timeout,
                capture_output=True,
            )
            return {
                "stdout": _decode_shell_output(result.stdout),
                "stderr": _decode_shell_output(result.stderr),
                "exit_code": result.returncode,
            }

        return await asyncio.to_thread(_run)


@dataclass
class LocalPythonComponent(PythonComponent):
    _work_dir: str = field(default="", repr=False)

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        work_dir = _resolve_work_dir(
            cwd=None,
            configured_work_dir=self._work_dir,
        )

        def _run() -> dict[str, Any]:
            try:
                result = subprocess.run(
                    [os.environ.get("PYTHON", sys.executable), "-c", code],
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                    cwd=work_dir,
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
    _extra_allowed_roots: list[str] = field(default_factory=list, repr=False)

    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path, self._extra_allowed_roots)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(abs_path, mode)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def read_file(self, path: str, encoding: str = "utf-8") -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path, self._extra_allowed_roots)
            with open(abs_path, encoding=encoding) as f:
                content = f.read()
            return {"success": True, "content": content}

        return await asyncio.to_thread(_run)

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path, self._extra_allowed_roots)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, mode, encoding=encoding) as f:
                f.write(content)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def delete_file(self, path: str) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = _ensure_safe_path(path, self._extra_allowed_roots)
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
            abs_path = _ensure_safe_path(path, self._extra_allowed_roots)
            entries = os.listdir(abs_path)
            if not show_hidden:
                entries = [e for e in entries if not e.startswith(".")]
            return {"success": True, "entries": entries}

        return await asyncio.to_thread(_run)


class LocalBooter(ComputerBooter):
    def __init__(self, work_dir: str = "") -> None:
        # Normalize work_dir to an absolute path once and use it consistently
        abs_work_dir = os.path.abspath(work_dir) if work_dir else ""
        self._work_dir = abs_work_dir
        self._extra_allowed_roots: list[str] = []

        # Auto-create work directory if configured and not exists
        if abs_work_dir:
            if not os.path.exists(abs_work_dir):
                try:
                    os.makedirs(abs_work_dir, exist_ok=True)
                    logger.info(f"Created local working directory: {abs_work_dir}")
                except OSError as e:
                    logger.warning(
                        f"Failed to create local working directory {abs_work_dir}: {e}"
                    )
            self._extra_allowed_roots = [abs_work_dir]

        self._fs = LocalFileSystemComponent(
            _extra_allowed_roots=self._extra_allowed_roots
        )
        self._python = LocalPythonComponent(_work_dir=abs_work_dir)
        self._shell = LocalShellComponent(
            _work_dir=abs_work_dir, _extra_allowed_roots=self._extra_allowed_roots
        )

    @property
    def work_dir(self) -> str:
        return self._work_dir

    async def boot(self, session_id: str) -> None:
        logger.info(f"Local computer booter initialized for session: {session_id}")

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
