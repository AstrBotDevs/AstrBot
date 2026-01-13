import asyncio
import random
from typing import Any

import aiohttp
import boxlite
from shipyard.filesystem import FileSystemComponent as ShipyardFileSystemComponent
from shipyard.python import PythonComponent as ShipyardPythonComponent
from shipyard.shell import ShellComponent as ShipyardShellComponent

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import SandboxBooter


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
        except asyncio.TimeoutError:
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
                logger.info(
                    f"Checking health for sandbox {ship_id} on {self.sb_url}..."
                )
                url = f"{self.sb_url}/health"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            logger.info(f"Sandbox {ship_id} is healthy")
                return
            except Exception:
                await asyncio.sleep(1)
                loop -= 1


class BoxliteBooter(SandboxBooter):
    async def boot(self, session_id: str) -> None:
        logger.info(
            f"Booting(Boxlite) for session: {session_id}, this may take a while..."
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
        logger.info(f"Boxlite booter started for session: {session_id}")
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
