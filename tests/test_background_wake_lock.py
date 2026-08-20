"""
回归测试: 后台任务唤醒路径应使用会话锁

背景: 用户消息处理路径(internal.py)通过 session_lock_manager 按会话串行化,
但后台任务唤醒路径(_wake_main_agent_for_background_result)直接跑 agent,
未获取会话锁 —— 与用户消息并发处理时导致上下文丢失。

本测试断言: 修复后, 唤醒流程必须获取会话锁 (acquire_lock 被调用)。
修复前该测试失败, 修复后通过。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor


def _make_run_context():
    """构造最小可用的 run_context mock"""
    event = SimpleNamespace(
        unified_msg_origin="Pstar:FriendMessage:TEST",
        role="friend",
        get_extra=lambda key: None,
    )
    ctx = SimpleNamespace(
        get_config=lambda umo: {},
        get_llm_tool_manager=MagicMock(),
        conversation_manager=MagicMock(update_conversation=AsyncMock()),
    )
    agent_ctx = SimpleNamespace(event=event, context=ctx)
    return SimpleNamespace(
        context=agent_ctx,
        tool_call_timeout=60,
    )


def _make_runner_mock():
    """构造假 agent runner: step_until_done 异步生成器"""
    runner = MagicMock()

    async def _step_until_done(*args, **kwargs):
        yield None

    runner.step_until_done.side_effect = _step_until_done
    runner.get_final_llm_resp.return_value = SimpleNamespace(completion_text="done")
    return runner


@pytest.mark.asyncio
async def test_background_wake_acquires_session_lock():
    """后台任务唤醒必须获取会话锁(与用户消息路径一致)"""
    run_context = _make_run_context()
    runner = _make_runner_mock()

    # 用 AsyncMock 追踪 acquire_lock 是否被调用
    lock_mgr = MagicMock()
    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = None
    lock_mgr.acquire_lock.return_value = lock_cm

    with (
        # create=True: 当前代码尚未引入 session_lock_manager, patch 尚不存在的属性
        patch("astrbot.core.astr_agent_tool_exec.session_lock_manager", lock_mgr, create=True),
        # _get_session_conv / build_main_agent 在函数内部 import, 需 patch 源模块
        patch(
            "astrbot.core.astr_main_agent._get_session_conv",
            new=AsyncMock(return_value=SimpleNamespace(history="[]", cid="conv-1")),
        ),
        patch(
            "astrbot.core.astr_main_agent.build_main_agent",
            new=AsyncMock(return_value=SimpleNamespace(agent_runner=runner)),
        ),
        patch("astrbot.core.astr_agent_tool_exec.CronMessageEvent"),
        patch("astrbot.core.astr_agent_tool_exec.MessageSession"),
    ):
        await FunctionToolExecutor._wake_main_agent_for_background_result(
            run_context,
            task_id="task-1",
            tool_name="transfer_to_x",
            result_text="some result",
            tool_args={},
            note="background task finished",
            summary_name="Dedicated to subagent `x`",
        )

    # 核心断言: 修复后必须获取会话锁, 且锁粒度为该会话
    lock_mgr.acquire_lock.assert_called_once()
    args = lock_mgr.acquire_lock.call_args[0]
    assert "Pstar:FriendMessage:TEST" in args, (
        f"会话锁应按 unified_msg_origin 获取, 实际参数: {args}"
    )
