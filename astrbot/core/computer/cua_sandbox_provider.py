from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from astrbot.api import logger
from astrbot.core.computer.booters import cua as cua_booter
from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.star.context import Context

BootHook = Callable[[Context, str, str, dict], Awaitable[ComputerBooter]]


async def _sync_skills_to_sandbox(booter: ComputerBooter) -> None:
    from astrbot.core.computer.computer_client import _sync_skills_to_sandbox as sync

    await sync(booter)


class CuaSandboxProvider:
    provider_id = "cua"

    def __init__(self, boot_hook: BootHook | None = None) -> None:
        self._boot_hook = boot_hook

    def build_create_config(self, context: Context, session_id: str) -> dict:
        config = context.get_config(umo=session_id)
        sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
        return cua_booter.build_cua_booter_kwargs(sandbox_cfg)

    def build_connect_info(self, sandbox_name: str, config: dict) -> dict:
        return {
            "name": sandbox_name,
            "local": config.get("local", True),
            "image": config.get("image"),
            "os_type": config.get("os_type"),
        }

    def get_idle_timeout(self, context: Context, session_id: str) -> float:
        config = context.get_config(umo=session_id)
        sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
        value = sandbox_cfg.get("cua_idle_timeout", 0)
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(timeout, 0.0)

    async def create_booter(
        self,
        context: Context,
        session_id: str,
        sandbox_id: str,
        config: dict,
    ) -> ComputerBooter:
        if self._boot_hook is not None:
            return await self._boot_hook(context, session_id, sandbox_id, config)
        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        client = cua_booter.CuaBooter(**config)
        started_at = time.monotonic()
        logger.info(
            "[Computer] CUA managed sandbox boot start: sandbox_id=%s session_id=%s boot_session_id=%s image=%s os_type=%s local=%s ttl=%s",
            sandbox_id,
            session_id,
            uuid_str,
            config.get("image"),
            config.get("os_type"),
            config.get("local"),
            config.get("ttl"),
        )
        try:
            await client.boot(uuid_str)
            setattr(client, "sandbox_id", sandbox_id)
            logger.info(
                "[Computer] CUA managed sandbox boot connected: sandbox_id=%s session_id=%s elapsed_ms=%d",
                sandbox_id,
                session_id,
                int((time.monotonic() - started_at) * 1000),
            )
            await _sync_skills_to_sandbox(client)
        except Exception:
            logger.warning(
                "[Computer] CUA managed sandbox boot failed: sandbox_id=%s session_id=%s elapsed_ms=%d",
                sandbox_id,
                session_id,
                int((time.monotonic() - started_at) * 1000),
                exc_info=True,
            )
            try:
                await client.shutdown()
            except Exception as shutdown_error:
                logger.warning(
                    "Failed to shutdown sandbox after boot error for session %s: %s",
                    session_id,
                    shutdown_error,
                )
            raise
        logger.info(
            "[Computer] CUA managed sandbox boot done: sandbox_id=%s session_id=%s elapsed_ms=%d",
            sandbox_id,
            session_id,
            int((time.monotonic() - started_at) * 1000),
        )
        return client

    async def destroy_booter(self, booter: ComputerBooter, record: dict) -> None:
        await booter.shutdown()
