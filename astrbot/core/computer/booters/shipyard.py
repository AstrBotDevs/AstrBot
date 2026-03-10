from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from shipyard import ShipyardClient, Spec

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


class ShipyardBooter(ComputerBooter):
    @classmethod
    @functools.cache
    def _default_tools(cls) -> tuple[FunctionTool, ...]:
        from astrbot.core.computer.tools.fs import FileDownloadTool, FileUploadTool
        from astrbot.core.computer.tools.python import PythonTool
        from astrbot.core.computer.tools.shell import ExecuteShellTool

        return (
            ExecuteShellTool(),
            PythonTool(),
            FileUploadTool(),
            FileDownloadTool(),
        )

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
        logger.info(
            "[Computer] sandbox_created booter=shipyard ship_id=%s session=%s",
            ship.id,
            session_id,
        )
        self._ship = ship

    async def shutdown(self) -> None:
        logger.info("[Computer] booter_shutdown booter=shipyard status=done")

    @property
    def fs(self) -> FileSystemComponent:
        return self._ship.fs

    @property
    def python(self) -> PythonComponent:
        return self._ship.python

    @property
    def shell(self) -> ShellComponent:
        return self._ship.shell

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to sandbox"""
        result = await self._ship.upload_file(path, file_name)
        logger.info(
            "[Computer] file_upload booter=shipyard remote_path=%s",
            file_name,
        )
        return result

    async def download_file(self, remote_path: str, local_path: str):
        """Download file from sandbox."""
        result = await self._ship.download_file(remote_path, local_path)
        logger.info(
            "[Computer] file_download booter=shipyard remote_path=%s local_path=%s",
            remote_path,
            local_path,
        )
        return result

    @classmethod
    def get_default_tools(cls) -> list[FunctionTool]:
        return list(cls._default_tools())

    async def available(self) -> bool:
        """Check if the sandbox is available."""
        try:
            ship_id = self._ship.id
            data = await self._sandbox_client.get_ship(ship_id)
            if not data:
                logger.debug(
                    "[Computer] health_check booter=shipyard ship_id=%s healthy=false reason=no_data",
                    ship_id,
                )
                return False
            health = bool(data.get("status", 0) == 1)
            logger.debug(
                "[Computer] health_check booter=shipyard ship_id=%s healthy=%s",
                ship_id,
                health,
            )
            return health
        except Exception:
            logger.exception(
                "[Computer] health_check_failed booter=shipyard ship_id=%s",
                getattr(getattr(self, "_ship", None), "id", "unknown"),
            )
            return False
