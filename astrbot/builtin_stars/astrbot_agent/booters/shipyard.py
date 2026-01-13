import os
import uuid

from shipyard import ShipyardClient, Spec

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import SandboxBooter


class ShipyardSandboxClient:
    _instance = None
    _initialized = False

    def __init__(self) -> None:
        if not ShipyardSandboxClient._initialized:
            self.endpoint = os.getenv("SHIPYARD_ENDPOINT", "http://localhost:8000")
            self.access_token = os.getenv("SHIPYARD_ACCESS_TOKEN", "")
            self.client = ShipyardClient(
                endpoint_url=self.endpoint, access_token=self.access_token
            )
            ShipyardSandboxClient._initialized = True

    def __new__(cls) -> "ShipyardSandboxClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


class ShipyardBooter(SandboxBooter):
    def __init__(self):
        self._sandbox_client = ShipyardSandboxClient()

    async def boot(self, session_id: str) -> None:
        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        ship = await self._sandbox_client.client.create_ship(
            ttl=3600,
            spec=Spec(cpus=1.0, memory="512m"),
            max_session_num=3,
            session_id=uuid_str,
        )
        logger.info(f"Got sandbox ship: {ship.id} for session: {session_id}")
        self._ship = ship

    async def shutdown(self) -> None:
        pass

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
        return await self._ship.upload_file(path, file_name)
