import os
import uuid
from typing import Literal

from astrbot.api import logger

from .booters.base import SandboxBooter


class SandboxClient:
    session_booter: dict[str, SandboxBooter] = {}

    def __init__(
        self, booter_type: Literal["shipyard-bay", "boxlite"] | None = None
    ) -> None:
        if booter_type is None:
            booter_type = os.getenv("ASTRBOT_SANDBOX_TYPE", "shipyard-bay")  # type: ignore
        self.booter_type = booter_type
        logger.info(f"SandboxClient initialized with booter type: {self.booter_type}")

    async def get_booter(self, session_id: str) -> SandboxBooter:
        if session_id not in self.session_booter:
            uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
            if self.booter_type == "shipyard-bay":
                from .booters.shipyard import ShipyardBooter

                self.client = ShipyardBooter()
            elif self.booter_type == "boxlite":
                from .booters.boxlite import ShipyardBooter

                self.client = ShipyardBooter()
            else:
                raise ValueError(f"Unknown booter type: {self.booter_type}")

            try:
                await self.client.boot(uuid_str)
            except Exception as e:
                logger.error(f"Error booting sandbox for session {session_id}: {e}")
                raise e

            self.session_booter[session_id] = self.client
        return self.session_booter[session_id]
