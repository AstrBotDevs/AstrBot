import uuid
from typing import Literal

from astrbot.api import logger

from .booters.base import SandboxBooter

session_booter: dict[str, SandboxBooter] = {}


class SandboxClient:
    @classmethod
    async def get_booter(
        cls,
        session_id: str,
        booter_type: Literal["shipyard", "boxlite"] = "shipyard",
    ) -> SandboxBooter:
        if session_id in session_booter:
            booter = session_booter[session_id]
            if not await booter.available():
                # rebuild
                session_booter.pop(session_id, None)
        if session_id not in session_booter:
            uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
            if booter_type == "shipyard":
                from .booters.shipyard import ShipyardBooter

                client = ShipyardBooter()
            elif booter_type == "boxlite":
                from .booters.boxlite import BoxliteBooter

                client = BoxliteBooter()
            else:
                raise ValueError(f"Unknown booter type: {booter_type}")

            try:
                await client.boot(uuid_str)
            except Exception as e:
                logger.error(f"Error booting sandbox for session {session_id}: {e}")
                raise e

            session_booter[session_id] = client
        return session_booter[session_id]
