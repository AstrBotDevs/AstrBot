"""Tests for PlatformManager."""

from asyncio import Queue
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.platform.manager import PlatformManager


@pytest.mark.asyncio
async def test_terminate_platform_removes_exact_instance_when_client_id_changes():
    """Terminate should remove the tracked instance even if client_self_id drifts."""
    config = MagicMock()
    config.__getitem__.side_effect = lambda key: {
        "platform": [],
        "platform_settings": {},
    }[key]

    manager = PlatformManager(config, Queue())
    stale_inst = MagicMock()
    stale_inst.client_self_id = "discord-client-new"
    active_inst = MagicMock()
    active_inst.client_self_id = "discord-client-live"

    manager.platform_insts = [stale_inst, active_inst]
    manager._inst_map["discord"] = {
        "inst": stale_inst,
        "client_id": "discord-client-old",
    }
    manager._terminate_inst_and_tasks = AsyncMock()

    await manager.terminate_platform("discord")

    assert manager.platform_insts == [active_inst]
    manager._terminate_inst_and_tasks.assert_awaited_once_with(stale_inst)
