from shipyard import ShipyardClient, Spec

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter


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

    async def download_file(self, remote_path: str, local_path: str):
        """Download file from sandbox."""
        return await self._ship.download_file(remote_path, local_path)

    async def available(self) -> bool:
        """Check if the sandbox is available."""
        try:
            ship_id = self._ship.id
            data = await self._sandbox_client.get_ship(ship_id)
            if not data:
                return False
            health = bool(data.get("status", 0) == 1)
            return health
        except Exception as e:
            logger.error(f"Error checking Shipyard sandbox availability: {e}")
            return False
