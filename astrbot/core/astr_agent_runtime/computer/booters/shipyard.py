from __future__ import annotations

import functools
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Protocol

from shipyard import FileSystemComponent as ShipyardFileSystemComponent
from shipyard import ShipyardClient, Spec
from shipyard.python import PythonComponent as ShipyardPythonComponent

from astrbot.api import logger
from astrbot.core.astr_agent_runtime.computer.booters.shell_background import (
    prepare_shell_command,
)
from astrbot.core.astr_agent_runtime.computer.booters.shipyard_payload import (
    maybe_model_dump as _maybe_model_dump,
)

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .shipyard_search_file_util import search_files_via_shell


def _flatten_shipyard_payload(result: object) -> dict[str, Any]:
    """Flatten the Shipyard SDK execution result envelope.

    Shipyard SDK 1.0.0 wraps every execution result in
    ``{"success": ..., "data": {...}, "error": ...}``, while older servers
    returned the fields at the top level. Merging both levels lets callers
    keep reading a single flat mapping.

    Args:
        result: Raw result returned by the Shipyard SDK.

    Returns:
        Flat mapping with the top-level fields plus the ``data`` fields; the
        ``data`` key itself is removed. Nested ``None`` values never overwrite
        a real top-level value, so an envelope ``error`` is not hidden by
        ``data.error = None``.
    """
    payload = _maybe_model_dump(result)
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload

    flat = dict(payload)
    for key, value in data.items():
        if key == "data" or value is None:
            continue
        # The envelope `success` describes the request itself, so a
        # command-level `data.success` must not turn a failed request into a
        # success.
        if key == "success" and flat.get("success") is False:
            continue
        flat[key] = value
    flat.pop("data", None)
    return flat


class _ShipyardShell(Protocol):
    """The SDK shell operations consumed by the adapter."""

    def exec(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int | None = 300,
    ) -> Awaitable[object]: ...


class ShipyardShellWrapper:
    def __init__(self, _shipyard_shell: _ShipyardShell):
        self._shell = _shipyard_shell

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,  # noqa: ASYNC109 - Preserve the existing timeout keyword contract.
        shell: bool = True,
        background: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if session_id is not None:
            raise NotImplementedError(
                "Shipyard shell execution does not support session_id"
            )
        if not shell:
            return {
                "stdout": "",
                "stderr": "error: only shell mode is supported in shipyard booter.",
                "exit_code": 2,
                "success": False,
            }

        run_command = prepare_shell_command(command, env, background)

        result = await self._shell.exec(
            run_command,
            timeout=timeout or 300,
            cwd=cwd,
        )
        payload = _flatten_shipyard_payload(result)

        # Shell output lives under `data` on SDK 1.0.0 and at the top level on
        # older servers; keep both shapes working.
        stdout = payload.get("output") or payload.get("stdout") or ""
        stderr = payload.get("error") or payload.get("stderr") or ""
        exit_code = payload.get("exit_code")
        if exit_code is None:
            exit_code = payload.get("return_code")
        success = payload.get("success")
        if success is None:
            # Older servers omit `success`; fall back to the exit code so a
            # failing command with quiet stderr is not reported as a success.
            success = exit_code in (0, None) and not stderr
        if background:
            pid: int | None = None
            try:
                pid = int(str(stdout).strip().splitlines()[-1])
            except Exception:
                pid = None
            return {
                "pid": pid,
                "stdout": (
                    f"Command is running in the background. pid={pid}"
                    if pid is not None
                    else "Command was submitted in the background."
                ),
                "stderr": stderr,
                "exit_code": exit_code,
                "success": bool(success),
                "execution_id": payload.get("execution_id"),
                "execution_time_ms": payload.get("execution_time_ms"),
                "command": payload.get("command"),
            }

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "success": bool(success),
            "execution_id": payload.get("execution_id"),
            "execution_time_ms": payload.get("execution_time_ms"),
            "command": payload.get("command"),
        }


class ShipyardFileSystemWrapper:
    def __init__(
        self, _shipyard_fs: ShipyardFileSystemComponent, _shipyard_shell: ShellComponent
    ):
        self._fs = _shipyard_fs
        self._shell = _shipyard_shell

    async def create_file(
        self, path: str, content: str = "", mode: int = 420
    ) -> dict[str, Any]:
        return _flatten_shipyard_payload(
            await self._fs.create_file(path=path, content=content, mode=mode)
        )

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return _flatten_shipyard_payload(
            await self._fs.read_file(
                path=path, encoding=encoding, offset=offset, limit=limit
            )
        )

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        return _flatten_shipyard_payload(
            await self._fs.write_file(
                path=path, content=content, mode=mode, encoding=encoding
            )
        )

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        return _flatten_shipyard_payload(
            await self._fs.list_dir(path=path, show_hidden=show_hidden)
        )

    async def delete_file(self, path: str) -> dict[str, Any]:
        return _flatten_shipyard_payload(await self._fs.delete_file(path=path))

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict[str, Any]:
        return await search_files_via_shell(
            self._shell,
            pattern=pattern,
            path=path,
            glob=glob,
            after_context=after_context,
            before_context=before_context,
        )

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        return _flatten_shipyard_payload(
            await self._fs.edit_file(
                path=path,
                old_string=old_string,
                new_string=new_string,
                replace_all=replace_all,
                encoding=encoding,
            )
        )


class ShipyardPythonWrapper:
    """Adapt the common Python contract to the SDK's kernel execution API."""

    def __init__(self, python: ShipyardPythonComponent) -> None:
        self._python = python

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,  # noqa: ASYNC109 - Preserve the shared timeout keyword contract.
        silent: bool = False,
        cwd: str | None = None,
    ) -> dict[str, object]:
        """Accept the default cwd without forwarding an unsupported SDK keyword."""
        if cwd is not None:
            raise NotImplementedError("Shipyard Python execution does not support cwd")
        return await self._python.exec(
            code, kernel_id=kernel_id, timeout=timeout, silent=silent
        )


class ShipyardBooter(ComputerBooter):
    def __init__(
        self,
        endpoint_url: str,
        access_token: str,
        ttl: int = 3600,
        session_num: int = 10,
    ) -> None:
        self._sandbox_client = ShipyardClient(
            endpoint_url=endpoint_url, access_token=access_token
        )
        self._ttl = ttl
        self._session_num = session_num

    async def boot(self, session_id: str) -> None:
        ship = await self._sandbox_client.create_ship(
            ttl=self._ttl,
            spec=Spec(cpus=1.0, memory="512m"),
            max_session_num=self._session_num,
            session_id=session_id,
        )
        logger.info(f"Got sandbox ship: {ship.id} for session: {session_id}")
        self._ship = ship
        self._shell = ShipyardShellWrapper(self._ship.shell)
        self._fs = ShipyardFileSystemWrapper(self._ship.fs, self._shell)

    async def shutdown(self, **kwargs) -> None:
        logger.info("[Computer] Shipyard booter shutdown.")

    @property
    def fs(self) -> FileSystemComponent:
        return self._fs

    @property
    def python(self) -> PythonComponent:
        return ShipyardPythonWrapper(self._ship.python)

    @property
    def shell(self) -> ShellComponent:
        return self._shell

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to sandbox"""
        result = await self._ship.upload_file(path, file_name)
        logger.info("[Computer] File uploaded to Shipyard sandbox: %s", file_name)
        return result

    async def download_file(self, remote_path: str, local_path: str):
        """Download file from sandbox."""
        result = await self._ship.download_file(remote_path, local_path)
        logger.info(
            "[Computer] File downloaded from Shipyard sandbox: %s -> %s",
            remote_path,
            local_path,
        )
        return result

    async def available(self) -> bool:
        """Check if the sandbox is available."""
        try:
            ship_id = self._ship.id
            data = await self._sandbox_client.get_ship(ship_id)
            if not data:
                logger.info(
                    "[Computer] Shipyard sandbox health check: id=%s, healthy=False (no data)",
                    ship_id,
                )
                return False
            health = bool(data.get("status", 0) == 1)
            logger.info(
                "[Computer] Shipyard sandbox health check: id=%s, healthy=%s",
                ship_id,
                health,
            )
            return health
        except Exception as e:
            logger.error(f"Error checking Shipyard sandbox availability: {e}")
            return False

    @classmethod
    @functools.cache
    def _default_tools(cls) -> tuple[ToolSchema, ...]:
        from astrbot.core.astr_agent_runtime.tools.computer_tools import (
            ExecuteShellTool,
            FileDownloadTool,
            FileUploadTool,
            PythonTool,
        )

        return (
            ExecuteShellTool(),
            PythonTool(),
            FileUploadTool(),
            FileDownloadTool(),
        )

    @classmethod
    def get_default_tools(cls) -> list[ToolSchema]:
        return list(cls._default_tools())


if TYPE_CHECKING:
    from astrbot.core.agent.tool import ToolSchema
