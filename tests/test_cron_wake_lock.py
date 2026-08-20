"""
回归测试: cron 定时任务唤醒路径也应使用会话锁

背景: 与后台任务唤醒(_wake_main_agent_for_background_result)相同,
cron 定时任务触发时直接跑 agent, 未获取会话锁 —— 与用户消息并发
处理时可能导致上下文丢失。

本测试断言: 修复后, cron 唤醒流程必须获取会话锁 (acquire_lock 被调用)。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.cron.manager import CronJobManager


def _make_manager():
    """构造最小可用的 CronJobManager mock"""
    ctx = SimpleNamespace(
        get_config=lambda umo: {"admins_id": [], "provider_settings": {}},
        get_llm_tool_manager=MagicMock(),
        conversation_manager=MagicMock(update_conversation=AsyncMock()),
    )
    mgr = CronJobManager.__new__(CronJobManager)  # 跳过 __init__, 只设 ctx
    mgr.ctx = ctx
    return mgr


def _make_runner_mock():
    runner = MagicMock()

    async def _step_until_done(*args, **kwargs):
        yield None

    runner.step_until_done.side_effect = _step_until_done
    runner.get_final_llm_resp.return_value = SimpleNamespace(
        completion_text="done", role="assistant"
    )
    return runner


@pytest.mark.asyncio
async def test_cron_wake_acquires_session_lock():
    """cron 定时任务唤醒必须获取会话锁(与用户消息/后台唤醒路径一致)"""
    mgr = _make_manager()
    runner = _make_runner_mock()

    lock_mgr = MagicMock()
    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = None
    lock_mgr.acquire_lock.return_value = lock_cm

    fake_cron_event = SimpleNamespace(
        unified_msg_origin="Pstar:FriendMessage:TEST", role="member"
    )

    with (
        patch(
            "astrbot.core.cron.manager.session_lock_manager", lock_mgr, create=True
        ),
        patch(
            "astrbot.core.astr_main_agent._get_session_conv",
            new=AsyncMock(return_value=SimpleNamespace(history="[]", cid="conv-1")),
        ),
        patch(
            "astrbot.core.astr_main_agent.build_main_agent",
            new=AsyncMock(return_value=SimpleNamespace(agent_runner=runner)),
        ),
        patch(
            "astrbot.core.cron.manager.CronMessageEvent",
            return_value=fake_cron_event,
        ),
        # MessageSession 需为真实类型(函数内 isinstance 判断), from_str 可解析字符串
    ):
        await mgr._woke_main_agent(
            message="test cron job",
            session_str="Pstar:FriendMessage:TEST",
            extras={"cron_job": {"id": "job-1", "name": "t", "run_started_at": "t"}},
        )

    # 核心断言: 修复后必须获取会话锁, 且锁粒度为该会话
    lock_mgr.acquire_lock.assert_called_once()
    args = lock_mgr.acquire_lock.call_args[0]
    assert "Pstar:FriendMessage:TEST" in args, (
        f"会话锁应按 unified_msg_origin 获取, 实际参数: {args}"
    )
