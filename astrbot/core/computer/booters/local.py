from __future__ import annotations

import asyncio
import locale
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from python_ripgrep import search

from astrbot.api import logger
from astrbot.core.computer.file_read_utils import (
    detect_text_encoding,
    read_local_text_range_sync,
)
from astrbot.core.utils.astrbot_path import get_astrbot_root

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


# WHY ``_NO_WINDOW_KWARGS``:
#   pythonw.exe (GUI subsystem) 启动下,spawn 一个 CUI 子进程 (cmd.exe /
#   python.exe) 时 Windows 默认会为子进程新开一个控制台窗口 — 即用户报告的
#   "弹 cmd 黑框" 现象。``creationflags=CREATE_NO_WINDOW`` 是消除该窗口的
#   标准做法。
#
#   跨平台:
#     - win32: 返回 ``{"creationflags": subprocess.CREATE_NO_WINDOW}``
#     - 其他: 返回 ``{}`` (non-Windows 上 ``CREATE_NO_WINDOW`` 不存在)
#
#   Refs:
#     - subprocess.CREATE_NO_WINDOW 只在 win32 平台上有定义
#     - asyncio.create_subprocess_exec 同样支持 ``creationflags`` kwarg
_NO_WINDOW_KWARGS: dict[str, int] = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)


# WHY ``_PYTHON_SUBPROCESS_PREAMBLE``:
#   ``_NO_WINDOW_KWARGS`` suppresses the console for the *direct* child of
#   AstrBot's computer booter (e.g. ``python.exe`` invoked by ``-c``), but
#   it does NOT propagate into user code. When a user-side script spawns
#   yet another CUI child via ``subprocess.run`` / ``subprocess.Popen``
#   without ``creationflags=CREATE_NO_WINDOW``, Windows allocates a brand
#   new console window because the current ``python.exe`` has no inherited
#   console to hand out — the nested "弹 cmd 黑框" case.
#
#   Mitigation: prepend a tiny idempotent snippet to user code that
#   monkey-patches ``subprocess.Popen`` to default-inject
#   ``creationflags=CREATE_NO_WINDOW`` AND a ``STARTUPINFO`` with
#   ``wShowWindow = SW_HIDE``. After this runs in the spawned interpreter
#   every common entry point (``subprocess.run`` / ``subprocess.call`` /
#   ``subprocess.check_output`` / direct ``Popen``) routes through the
#   patched class. The patch is itself flagged via
#   ``_ab_no_window_patched`` so re-execution (e.g. via ``python -c``
#   invoked twice) cannot stack-wrap.
#
#   Naming note: identifiers use a single leading underscore rather than
#   the dunder form so CPython's name-mangling does NOT rewrite them to
#   ``_ClassName__name`` when they appear inside the patched class body.
#
#   Out-of-scope (not patched, accepted edge cases):
#     - ``from subprocess import Popen`` captured before this preamble runs.
#     - Direct ctypes / ``os.spawn*`` / ``os.system`` / ``os.popen`` calls.
#   These cover the >95% agent-written spawn paths without a heavy module
#   rewrite.
_PYTHON_SUBPROCESS_PREAMBLE: str = (
    "import subprocess as _ab_sp\n"
    "import sys as _ab_sys\n"
    "if _ab_sys.platform == 'win32':\n"
    "    _ab_cnw = getattr(_ab_sp, 'CREATE_NO_WINDOW', 0x08000000)\n"
    "    _ab_orig_popen = getattr(_ab_sp, 'Popen', None)\n"
    "    if _ab_orig_popen is not None and not getattr(\n"
    "        _ab_orig_popen, '_ab_no_window_patched', False\n"
    "    ):\n"
    "        class _ab_no_window_popen(_ab_orig_popen):\n"
    "            _ab_no_window_patched = True\n"
    "\n"
    "            def __init__(self, *args, **kwargs):\n"
    "                cf = kwargs.get('creationflags') or 0\n"
    "                if not (cf & _ab_cnw):\n"
    "                    kwargs['creationflags'] = cf | _ab_cnw\n"
    "                si = kwargs.get('startupinfo')\n"
    "                if si is None:\n"
    "                    si = _ab_sp.STARTUPINFO()\n"
    "                    kwargs['startupinfo'] = si\n"
    "                si.dwFlags |= 0x00000001  # STARTF_USESHOWWINDOW\n"
    "                si.wShowWindow = 0  # SW_HIDE\n"
    "                super().__init__(*args, **kwargs)\n"
    "\n"
    "        _ab_sp.Popen = _ab_no_window_popen\n"
)


def _is_safe_command(command: str) -> bool:
    cmd = f" {command.strip().lower()} "
    return not any(pat in cmd for pat in _BLOCKED_COMMAND_PATTERNS)


def _self_pids() -> frozenset[int]:
    """Return the PIDs that must never be killed by the local shell tool.

    Includes the current AstrBot process, its parent, and the process group
    leader so that indirect kills (for example ``kill -9 -$PGID``) are also
    blocked. On Windows ``os.getpgrp`` is unavailable, so the set only
    contains the current process and its parent in that case.
    """
    pids: set[int] = {os.getpid(), os.getppid()}
    getpgrp = getattr(os, "getpgrp", None)
    if getpgrp is not None:
        try:
            pgid = getpgrp()
        except (OSError, AttributeError):
            pgid = 0
        if pgid and pgid > 0:
            pids.add(pgid)
    return frozenset(pids)


# Commands that, in the local runtime, would match the running AstrBot /
# Python process when invoked without an explicit PID. They are refused
# regardless of the argument so an agent cannot iterate the process list
# (for example via ``pgrep`` + ``pkill``) to discover the protected PID.
_SELF_KILL_NAME_PATTERNS = (
    "taskkill",  # Windows: kill by PID / IM / window title
    "stop-process",  # PowerShell: kill by name or PID
    "pkill",  # Unix: kill by pattern match
    "killall",  # Unix: kill by exact process name
    "pgrep",  # Unix: process lookup (often paired with pkill)
)


def _would_kill_self(command: str) -> bool:
    """Best-effort detection of commands that target the host AstrBot process.

    Complements the substring blacklist in :data:`_BLOCKED_COMMAND_PATTERNS` by
    inspecting command tokens for kill patterns that target protected PIDs and
    for name-based kill commands that would match the running Python process.

    This is intentionally conservative for the local runtime where the shell
    command runs in the same OS instance as AstrBot. The sandbox runtime is
    not affected because its commands execute in an isolated container.
    """
    lowered = command.lower()
    protected = _self_pids()

    # Explicit numeric PID kill, e.g. `kill 1234`, `kill -15 1234`,
    # `kill -TERM 1234`. `kill -9` is already covered by the blacklist but
    # is matched here as well for any other signal number.
    for match in re.finditer(r"\bkill\b\s+((?:-\w+\s+)*)(\d+)", lowered):
        try:
            pid = int(match.group(2))
        except ValueError:
            continue
        if pid in protected:
            return True

    return any(keyword in lowered for keyword in _SELF_KILL_NAME_PATTERNS)


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
class LocalShellComponent(ShellComponent):
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
        if _would_kill_self(command):
            raise PermissionError(
                "Blocked: refusing to terminate the AstrBot host process."
            )

        def _run() -> dict[str, Any]:
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})
            working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
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
                    **_NO_WINDOW_KWARGS,
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}
            # `command` is intentionally executed through the current shell so
            # local computer-use behavior matches existing tool semantics.
            # Safety relies on `_is_safe_command()` and the allowed-root checks.
            proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                command,
                shell=shell,
                cwd=working_dir,
                env=run_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **_NO_WINDOW_KWARGS,
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
                            **_NO_WINDOW_KWARGS,
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


@dataclass
class LocalPythonComponent(PythonComponent):
    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        # Prepend a tiny monkey-patch of ``subprocess.Popen`` so that any
        # user-side ``subprocess.run`` / ``subprocess.Popen`` nested call
        # inside the spawned interpreter also suppresses its own console
        # window. Without this, a user ``subprocess.run(['cmd.exe', ...])``
        # would still flash a black console even though the parent
        # ``python.exe`` was already launched with ``CREATE_NO_WINDOW``.
        # See ``_PYTHON_SUBPROCESS_PREAMBLE`` for the patch details.
        wrapped_code = _PYTHON_SUBPROCESS_PREAMBLE + code

        def _run() -> dict[str, Any]:
            try:
                working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
                result = subprocess.run(
                    [
                        os.environ.get("PYTHON", sys.executable),
                        "-c",
                        wrapped_code,
                    ],
                    timeout=timeout,
                    capture_output=True,
                    cwd=working_dir,
                    # pythonw.exe 启动下抑制 python.exe 子进程黑窗;非 Windows 上为 {}
                    **_NO_WINDOW_KWARGS,
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
            results = search(
                patterns=[pattern],
                paths=[path] if path else None,
                globs=[glob] if glob else None,
                after_context=after_context,
                before_context=before_context,
                line_number=True,
            )
            return {"success": True, "content": _truncate_long_lines("".join(results))}

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
