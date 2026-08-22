"""Tests for duplicate platform ID detection in PlatformManager.load_platform.

Bug 背景(#9742)：多个平台适配器配置了相同的 id 时，主动消息
（cron / send_message_to_user 等）按 platform ID 路由并取第一个匹配，
导致消息总是通过第一个适配器（错误的 QQ 账号）发出。

修复：load_platform 检测到重复 ID 时拒绝加载后续同 ID 适配器并记录
错误日志，保证 ID 与账号的映射唯一。
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from astrbot.core.platform.manager import PlatformManager
from astrbot.core.star.star_handler import star_handlers_registry


class _FakeAstrBotConfig(dict):
    def save_config(self) -> None:
        pass


def _aiocq_config(platform_id: str, port: int) -> dict:
    return {
        "id": platform_id,
        "type": "aiocqhttp",
        "enable": True,
        "ws_reverse_host": "127.0.0.1",
        "ws_reverse_port": port,
        "ws_reverse_token": "",
    }


@pytest.fixture
def manager(monkeypatch) -> PlatformManager:
    monkeypatch.setattr(
        star_handlers_registry, "get_handlers_by_event_type", lambda *_: []
    )
    mgr = PlatformManager(
        _FakeAstrBotConfig({"platform": [], "platform_settings": {}}),
        asyncio.Queue(),
    )
    mgr._start_platform_task = MagicMock()
    return mgr


@pytest.mark.asyncio
async def test_duplicate_platform_id_is_skipped(manager):
    """相同 id 的第二个适配器应被拒绝加载，只保留第一个实例。"""
    await manager.load_platform(_aiocq_config("r01_ob", 6199))
    await manager.load_platform(_aiocq_config("r01_ob", 6191))

    aiocq_insts = [
        inst for inst in manager.platform_insts if inst.meta().id == "r01_ob"
    ]
    assert len(aiocq_insts) == 1
    # 第二个适配器的端口是 6191，被加载的是第一个(6199)
    assert aiocq_insts[0].port == 6199
    assert set(manager._inst_map.keys()) == {"r01_ob"}


@pytest.mark.asyncio
async def test_distinct_platform_ids_both_loaded(manager):
    """不同 id 的适配器不受影响，均正常加载。"""
    await manager.load_platform(_aiocq_config("bot_a", 6199))
    await manager.load_platform(_aiocq_config("bot_b", 6191))

    loaded_ids = {inst.meta().id for inst in manager.platform_insts}
    assert loaded_ids == {"bot_a", "bot_b"}
    assert set(manager._inst_map.keys()) == {"bot_a", "bot_b"}


@pytest.mark.asyncio
async def test_disabled_duplicate_not_loaded(manager):
    """disabled 的适配器不参与加载，也不触发重复检测。"""
    disabled = _aiocq_config("r01_ob", 6191)
    disabled["enable"] = False

    await manager.load_platform(_aiocq_config("r01_ob", 6199))
    await manager.load_platform(disabled)

    assert len(manager.platform_insts) == 1
