from __future__ import annotations

import asyncio
import functools
import random
from typing import TYPE_CHECKING, Any

import aiohttp
import boxlite
from shipyard.filesystem import FileSystemComponent as ShipyardFileSystemComponent
from shipyard.python import PythonComponent as ShipyardPythonComponent
from shipyard.shell import ShellComponent as ShipyardShellComponent

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


class MockShipyardSandboxClient:
    def __init__(self, sb_url: str) -> None:
        self.sb_url = sb_url.rstrip("/")

    async def _exec_operation(
        self,
        ship_id: str,
        operation_type: str,
        payload: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            headers = {"X-SESSION-ID": session_id}
            async with session.post(
                f"{self.sb_url}/{operation_type}",
                json=payload,
                headers=headers,
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to exec operation: {response.status} {error_text}"
                    )

    async def upload_file(self, path: str, remote_path: str) -> dict:
        """Upload a file to the sandbox"""
        url = f"http://{self.sb_url}/upload"

        try:
            # Read file content
            with open(path, "rb") as f:
                file_content = f.read()

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field(
                "file",
                file_content,
                filename=remote_path.split("/")[-1],
                content_type="application/octet-stream",
            )
            data.add_field("file_path", remote_path)

            timeout = aiohttp.ClientTimeout(total=120)  # 2 minutes for file upload

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        logger.info(
                            "[Computer] file_upload booter=boxlite remote_path=%s",
                            remote_path,
                        )
                        return {
                            "success": True,
                            "message": "File uploaded successfully",
                            "file_path": remote_path,
                        }
                    else:
                        error_text = await response.text()
                        logger.warning(
                            "[Computer] file_upload_failed booter=boxlite error=http_status status=%s remote_path=%s",
                            response.status,
                            remote_path,
                        )
                        return {
                            "success": False,
                            "error": f"Server returned {response.status}: {error_text}",
                            "message": "File upload failed",
                        }

        except aiohttp.ClientError as e:
            logger.error("[Computer] file_upload_failed booter=boxlite error=%s", e)
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
                "message": "File upload failed",
            }
        except asyncio.TimeoutError:
            logger.warning(
                "[Computer] file_upload_failed booter=boxlite error=timeout remote_path=%s",
                remote_path,
            )
            return {
                "success": False,
                "error": "File upload timeout",
                "message": "File upload failed",
            }
        except FileNotFoundError:
            logger.error(
                "[Computer] file_upload_failed booter=boxlite error=file_not_found path=%s",
                path,
            )
            return {
                "success": False,
                "error": f"File not found: {path}",
                "message": "File upload failed",
            }
        except Exception as exc:
            logger.exception(
                "[Computer] file_upload_failed booter=boxlite error=unexpected"
            )
            return {
                "success": False,
                "error": f"Internal error: {str(exc)}",
                "message": "File upload failed",
            }

    async def wait_healthy(self, ship_id: str, session_id: str) -> None:
        """Mock wait healthy"""
        loop = 60
        while loop > 0:
            try:
                logger.debug(
                    "[Computer] health_check booter=boxlite ship_id=%s session=%s endpoint=%s attempt=%s healthy=pending",
                    ship_id,
                    session_id,
                    self.sb_url,
                    61 - loop,
                )
                url = f"{self.sb_url}/health"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            logger.debug(
                                "[Computer] health_check booter=boxlite ship_id=%s session=%s endpoint=%s healthy=true",
                                ship_id,
                                session_id,
                                self.sb_url,
                            )
                            return
                await asyncio.sleep(1)
                loop -= 1
            except Exception:
                await asyncio.sleep(1)
                loop -= 1
        logger.warning(
            "[Computer] health_check_timeout booter=boxlite ship_id=%s session=%s endpoint=%s",
            ship_id,
            session_id,
            self.sb_url,
        )


class BoxliteBooter(ComputerBooter):
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

    async def boot(self, session_id: str) -> None:
        logger.info(
            "[Computer] booter_boot booter=boxlite session=%s status=starting",
            session_id,
        )
        random_port = random.randint(20000, 30000)
        self.box = boxlite.SimpleBox(
            image="soulter/shipyard-ship",
            memory_mib=512,
            cpus=1,
            ports=[
                {
                    "host_port": random_port,
                    "guest_port": 8123,
                }
            ],
        )
        await self.box.start()
        logger.info(
            "[Computer] booter_boot booter=boxlite session=%s status=ready ship_id=%s",
            session_id,
            self.box.id,
        )
        self.mocked = MockShipyardSandboxClient(
            sb_url=f"http://127.0.0.1:{random_port}"
        )
        self._fs = ShipyardFileSystemComponent(
            client=self.mocked,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._python = ShipyardPythonComponent(
            client=self.mocked,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._shell = ShipyardShellComponent(
            client=self.mocked,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )

        await self.mocked.wait_healthy(self.box.id, session_id)

    async def shutdown(self) -> None:
        logger.info(
            "[Computer] booter_shutdown booter=boxlite ship_id=%s status=starting",
            self.box.id,
        )
        self.box.shutdown()
        logger.info(
            "[Computer] booter_shutdown booter=boxlite ship_id=%s status=done",
            self.box.id,
        )

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
        """Upload file to sandbox"""
        return await self.mocked.upload_file(path, file_name)

    @classmethod
    def get_default_tools(cls) -> list[FunctionTool]:
        return list(cls._default_tools())
