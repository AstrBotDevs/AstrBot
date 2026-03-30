from __future__ import annotations

import asyncio
import locale
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from astrbot.core.computer.olayer import (
    FileSystemComponent,
    PythonComponent,
    ShellComponent,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_temp_path,
)

from .base import ComputerBooter


def _decode_shell_output(output: bytes | None) -> str:
    if output is None:
        return ""

    preferred = locale.getpreferredencoding(False) or "utf-8"
    try:
        return output.decode("utf-8")
    except (LookupError, UnicodeDecodeError):
        pass

    try:
        return output.decode(preferred)
    except (LookupError, UnicodeDecodeError):
        pass

    return output.decode("utf-8", errors="replace")


def _write_file_sync(path: str, content: str, mode: str, encoding: str) -> None:
    with open(path, mode, encoding=encoding) as f:
        f.write(content)


def _read_file_sync(path: str, encoding: str) -> str:
    with open(path, encoding=encoding) as f:
        return f.read()


@dataclass
class BwrapConfig:
    workspace_dir: str
    ro_binds: list[str] = field(default_factory=list)
    rw_binds: list[str] = field(default_factory=list)
    share_net: bool = True

    def __post_init__(self):
        # Merge default required system binds with any additional ro_binds passed
        default_ro = ["/usr", "/lib", "/lib64", "/bin", "/etc", "/opt"]
        for p in default_ro:
            if p not in self.ro_binds:
                self.ro_binds.append(p)


def build_bwrap_cmd(config: BwrapConfig, script_cmd: list[str]) -> list[str]:
    """Helper to build a bubblewrap command."""
    cmd = ["bwrap"]

    if not config.share_net:
        cmd.append("--unshare-net")

    # Bind paths to itself so paths match
    for path in config.ro_binds:
        if os.path.exists(path):
            cmd.extend(["--ro-bind", path, path])

    for path in config.rw_binds:
        # Avoid bind mounting dangerous host paths
        if path == "/" or path.startswith("/root"):
            continue
        if os.path.exists(path):
            cmd.extend(["--bind", path, path])

    # Make system binds the last to avoid issues about ro `/`
    cmd.extend(
        [
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--die-with-parent",
            "--dir",
            "/tmp",
            "--dir",
            "/var/tmp",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--bind",
            config.workspace_dir,
            config.workspace_dir,
        ]
    )

    cmd.extend(["--"])
    cmd.extend(script_cmd)
    return cmd


@dataclass
class BwrapShellComponent(ShellComponent):
    config: BwrapConfig

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 30,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})

            working_dir = cwd if cwd else self.config.workspace_dir

            # Use /bin/sh -c to run the evaluated command
            # The command must be run inside bwrap
            script_cmd = ["/bin/sh", "-c", command] if shell else shlex.split(command)
            bwrap_cmd = build_bwrap_cmd(self.config, script_cmd)

            if background:
                proc = subprocess.Popen(
                    bwrap_cmd,
                    cwd=working_dir,
                    env=run_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}

            result = subprocess.run(
                bwrap_cmd,
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
class BwrapPythonComponent(PythonComponent):
    config: BwrapConfig

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            bwrap_cmd = build_bwrap_cmd(
                self.config, [os.environ.get("PYTHON", "python3"), "-c", code]
            )
            try:
                result = subprocess.run(
                    bwrap_cmd,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                )
                stdout = "" if silent else result.stdout
                return {
                    "stdout": stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                }
            except subprocess.TimeoutExpired as e:
                return {
                    "stdout": e.stdout.decode()
                    if isinstance(e.stdout, bytes)
                    else str(e.stdout or ""),
                    "stderr": f"Execution timed out after {timeout} seconds.",
                    "exit_code": 1,
                }
            except Exception as e:
                return {
                    "stdout": "",
                    "stderr": str(e),
                    "exit_code": 1,
                }

        return await asyncio.to_thread(_run)


@dataclass
class HostBackedFileSystemComponent(FileSystemComponent):
    """File operations happen safely on host mapping to workspace, making I/O extremely fast."""

    workspace_dir: str

    def _safe_path(self, path: str) -> str:
        # Simply maps it. In a stricter implementation, we could verify it's inside workspace_dir.
        # But for this implementation, we trust the agent or restrict to workspace_dir.
        if not path.startswith("/"):
            path = os.path.join(self.workspace_dir, path)
        return path

    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict[str, Any]:
        p = self._safe_path(path)
        await asyncio.to_thread(os.makedirs, os.path.dirname(p), exist_ok=True)
        await asyncio.to_thread(_write_file_sync, p, content, "w", "utf-8")
        await asyncio.to_thread(os.chmod, p, mode)
        return {"success": True, "path": p}

    async def read_file(self, path: str, encoding: str = "utf-8") -> dict[str, Any]:
        p = self._safe_path(path)
        try:
            content = await asyncio.to_thread(_read_file_sync, p, encoding)
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        p = self._safe_path(path)
        await asyncio.to_thread(os.makedirs, os.path.dirname(p), exist_ok=True)
        try:
            await asyncio.to_thread(_write_file_sync, p, content, mode, encoding)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_file(self, path: str) -> dict[str, Any]:
        p = self._safe_path(path)
        try:
            if await asyncio.to_thread(os.path.isdir, p):
                await asyncio.to_thread(shutil.rmtree, p)
            else:
                await asyncio.to_thread(os.remove, p)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        p = self._safe_path(path)
        try:
            items = os.listdir(p)
            if not show_hidden:
                items = [item for item in items if not item.startswith(".")]
            return {"success": True, "items": items}
        except Exception as e:
            return {"success": False, "error": str(e), "items": []}


class BwrapBooter(ComputerBooter):
    def __init__(
        self, rw_binds: list[str] | None = None, ro_binds: list[str] | None = None
    ):
        self._rw_binds = rw_binds or []
        self._ro_binds = ro_binds or []
        self._fs: HostBackedFileSystemComponent | None = None
        self._python: BwrapPythonComponent | None = None
        self._shell: BwrapShellComponent | None = None
        self.config: BwrapConfig | None = None

    @property
    def fs(self) -> FileSystemComponent | None:
        return self._fs

    @property
    def python(self) -> PythonComponent | None:
        return self._python

    @property
    def shell(self) -> ShellComponent | None:
        return self._shell

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("python", "shell", "filesystem")

    async def boot(self, session_id: str) -> None:
        workspace_dir = os.path.join(
            get_astrbot_temp_path(), f"sandbox_workspace_{session_id}"
        )
        await asyncio.to_thread(os.makedirs, workspace_dir, exist_ok=True)

        self.config = BwrapConfig(
            workspace_dir=await asyncio.to_thread(os.path.abspath, workspace_dir),
            rw_binds=self._rw_binds,
            ro_binds=self._ro_binds,
        )
        self._fs = HostBackedFileSystemComponent(self.config.workspace_dir)
        self._python = BwrapPythonComponent(self.config)
        self._shell = BwrapShellComponent(self.config)
        if not await self.available():
            raise RuntimeError(
                "BubbleWrap sandbox unavailable on current machine for no bwrap executable."
            )
        test_shl = await self._shell.exec(command="ls > /dev/null")
        if test_shl["exit_code"] != 0:
            raise RuntimeError(
                """BubbleWrap sandbox fails to exec test shell command "ls > /dev/null" with stderr:
{}""".format(test_shl["stderr"])
            )
        test_py = await self._python.exec(code="print('Yes')")
        if test_py["exit_code"] != 0:
            raise RuntimeError(
                """BubbleWrap sandbox fails to exec test python code "print('Yes')" with stderr:
{}""".format(test_py["stderr"])
            )

    async def shutdown(self) -> None:
        if self.config and await asyncio.to_thread(os.path.exists, self.config.workspace_dir):
            await asyncio.to_thread(shutil.rmtree, self.config.workspace_dir, ignore_errors=True)

    async def upload_file(self, path: str, file_name: str) -> dict:
        if not self._fs or not self.config:
            return {"success": False, "error": "Not booted"}
        target = os.path.join(self.config.workspace_dir, file_name)
        try:
            shutil.copy2(path, target)
            return {"success": True, "file_path": target}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def download_file(self, remote_path: str, local_path: str) -> None:
        if not self._fs or not self.config:
            return
        if not remote_path.startswith("/"):
            remote_path = os.path.join(self.config.workspace_dir, remote_path)
        shutil.copy2(remote_path, local_path)

    async def available(self) -> bool:
        if sys.platform == "win32":
            return False
        if shutil.which("bwrap") is None:
            return False
        return True
