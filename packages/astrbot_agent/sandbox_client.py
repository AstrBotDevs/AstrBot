import os
from shipyard import ShipyardClient, SessionShip, Spec


class SandboxClient:
    _instance = None
    _initialized = False
    session_ship: dict[str, SessionShip] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SandboxClient, cls).__new__(cls)
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
            ship = await self.client.create_ship(
                ttl=3600,
                spec=Spec(cpus=0.5, memory="256m"),
                max_session_num=2,
                session_id=session_id,
            )
            self.session_ship[session_id] = ship
        return self.session_ship[session_id]

    def get_client(self) -> ShipyardClient:
        return self.client
