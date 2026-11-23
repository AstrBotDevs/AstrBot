from __future__ import annotations

import asyncio
import functools
import random
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

import aiohttp
import boxlite
from shipyard import FileSystemComponent as ShipyardFileSystemComponent
from shipyard import ShipyardClient
from shipyard.python import PythonComponent as ShipyardPythonComponent
from shipyard.shell import ShellComponent as ShipyardShellComponent

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .shipyard import (
    ShipyardFileSystemWrapper,
    ShipyardPythonWrapper,
    ShipyardShellWrapper,
)


class _BoxlitePort(TypedDict):
    host_port: int
    guest_port: int


class _BoxliteInstance(Protocol):
    @property
    def id(self) -> str: ...

    async def start(self) -> object: ...

    def shutdown(self) -> None: ...


class _BoxliteSDK(Protocol):
    """The optional Boxlite SDK surface used by this booter."""

    def SimpleBox(
        self,
        *,
        image: str,
        memory_mib: int,
        cpus: int,
        ports: list[_BoxlitePort],
    ) -> _BoxliteInstance: ...


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
        url = f"{self.sb_url}/upload"

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
                            "[Computer] File uploaded to Boxlite sandbox: %s",
                            remote_path,
                        )
                        return {
                            "success": True,
                            "message": "File uploaded successfully",
                            "file_path": remote_path,
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"Server returned {response.status}: {error_text}",
                            "message": "File upload failed",
                        }

        except aiohttp.ClientError as e:
            logger.error(f"Failed to upload file: {e}")
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
                "message": "File upload failed",
            }
        except TimeoutError:
            return {
                "success": False,
                "error": "File upload timeout",
                "message": "File upload failed",
            }
        except FileNotFoundError:
            logger.error(f"File not found: {path}")
            return {
                "success": False,
                "error": f"File not found: {path}",
                "message": "File upload failed",
            }
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {e}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}",
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


class _BoxliteShipyardClient(ShipyardClient):
    """Adapt direct sandbox operations to the nominal Shipyard SDK client API.

    The Boxlite transport has no Bay endpoint or authentication. SDK components
    use its execution and upload operations while the legacy transport retains
    the direct upload signature consumed by the booter.
    """

    def __init__(self, sandbox: MockShipyardSandboxClient) -> None:
        self._sandbox = sandbox
        self.endpoint_url = sandbox.sb_url
        self.access_token = None
        self._session: aiohttp.ClientSession | None = None

    async def _exec_operation(
        self,
        ship_id: str,
        operation_type: str,
        payload: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        return await self._sandbox._exec_operation(
            ship_id, operation_type, payload, session_id
        )

    async def upload_file(
        self, ship_id: str, file_path: str, session_id: str, remote_file_path: str
    ) -> dict[str, Any]:
        return await self._sandbox.upload_file(file_path, remote_file_path)


class BoxliteBooter(ComputerBooter):
    async def boot(self, session_id: str) -> None:
        logger.info(
            f"Booting(Boxlite) for session: {session_id}, this may take a while..."
        )
        random_port = random.randint(20000, 30000)
        self.box = cast(_BoxliteSDK, boxlite).SimpleBox(
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
        logger.info(f"Boxlite booter started for session: {session_id}")
        self.mocked = MockShipyardSandboxClient(
            sb_url=f"http://127.0.0.1:{random_port}"
        )
        sdk_client = _BoxliteShipyardClient(self.mocked)
        self._python = ShipyardPythonWrapper(
            ShipyardPythonComponent(
                client=sdk_client,
                ship_id=self.box.id,
                session_id=session_id,
            )
        )
        sdk_shell = ShipyardShellComponent(
            client=sdk_client,
            ship_id=self.box.id,
            session_id=session_id,
        )
        # Boxlite talks to the same Shipyard exec API, so its results carry the
        # same `data` envelope; wrap the shell before handing it to the file
        # system wrapper (file search reuses the shell) and to callers.
        self._shell = ShipyardShellWrapper(sdk_shell)
        self._ship_fs = ShipyardFileSystemComponent(
            client=sdk_client,
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._fs = ShipyardFileSystemWrapper(
            _shipyard_fs=self._ship_fs, _shipyard_shell=self._shell
        )

        await self.mocked.wait_healthy(self.box.id, session_id)

    async def shutdown(self, **kwargs) -> None:
        logger.info(f"Shutting down Boxlite booter for ship: {self.box.id}")
        self.box.shutdown()
        logger.info(f"Boxlite booter for ship: {self.box.id} stopped")

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

    async def available(self) -> bool:
        return hasattr(self, "box")


if TYPE_CHECKING:
    from astrbot.core.agent.tool import ToolSchema
