import uuid

from astrbot.api import logger
from astrbot.core.star.context import Context

from .booters.base import SandboxBooter

session_booter: dict[str, SandboxBooter] = {}


async def get_booter(
    context: Context,
    session_id: str,
) -> SandboxBooter:
    config = context.get_config(umo=session_id)

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    booter_type = sandbox_cfg.get("booter", "shipyard")

    if session_id in session_booter:
        booter = session_booter[session_id]
        if not await booter.available():
            # rebuild
            session_booter.pop(session_id, None)
    if session_id not in session_booter:
        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        if booter_type == "shipyard":
            from .booters.shipyard import ShipyardBooter

            ep = sandbox_cfg.get("shipyard_endpoint", "")
            token = sandbox_cfg.get("shipyard_access_token", "")
            ttl = sandbox_cfg.get("shipyard_ttl", 3600)
            max_sessions = sandbox_cfg.get("shipyard_max_sessions", 10)

            client = ShipyardBooter(
                endpoint_url=ep, access_token=token, ttl=ttl, session_num=max_sessions
            )
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
