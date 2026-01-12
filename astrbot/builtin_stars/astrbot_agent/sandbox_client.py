import os
import uuid

from shipyard import SessionShip, ShipyardClient, Spec

from astrbot.api import logger


class SandboxClient:
    _instance = None
    _initialized = False
    session_ship: dict[str, SessionShip] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not SandboxClient._initialized:
            self.endpoint = os.getenv("SHIPYARD_ENDPOINT", "http://localhost:8000")
            self.access_token = os.getenv("SHIPYARD_ACCESS_TOKEN", "")
            self.client = ShipyardClient(
                endpoint_url=self.endpoint, access_token=self.access_token
            )
            SandboxClient._initialized = True

    async def get_ship(self, session_id: str) -> SessionShip:
        if session_id not in self.session_ship:
            uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
            ship = await self.client.create_ship(
                ttl=3600,
                spec=Spec(cpus=1.0, memory="512m"),
                max_session_num=3,
                session_id=uuid_str,
            )
            logger.info(f"Got sandbox ship: {ship.id} for session: {session_id}")
            self.session_ship[session_id] = ship
        return self.session_ship[session_id]

    def get_client(self) -> ShipyardClient:
        return self.client
