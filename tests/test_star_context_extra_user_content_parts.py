"""回归测试：Context.tool_loop_agent() 必须把 extra_user_content_parts 透传给 ProviderRequest。

修复前该字段只存在于 ProviderRequest 与主流程 astr_main_agent，插件经
tool_loop_agent() 起子代理时无处放置「每轮现算、不应写入对话历史」的内容。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.message import TextPart
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context


class _FakeRunner:
    """只记录 reset() 收到的 ProviderRequest，不跑真实步骤。"""

    def __init__(self) -> None:
        self.request = None

    async def reset(self, *, request, **kwargs) -> None:
        self.request = request

    async def step_until_done(self, max_steps):
        for _ in ():  # 空 async 生成器：循环体一次都不进
            yield None

    def get_final_llm_resp(self):
        return SimpleNamespace(role="assistant", completion_text="")


def _build_context() -> Context:
    """构造只带 provider_manager 的 Context（绕过 __init__ 的重依赖）。"""
    ctx = Context.__new__(Context)
    ctx.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=MagicMock(spec=Provider))
    )
    return ctx


async def _run_tool_loop_agent(**kwargs):
    ctx = _build_context()
    runner = _FakeRunner()
    with (
        patch("astrbot.core.star.context.ToolLoopAgentRunner", return_value=runner),
        patch("astrbot.core.astr_agent_tool_exec.FunctionToolExecutor"),
        patch("astrbot.core.astr_agent_context.AgentContextWrapper"),
    ):
        await ctx.tool_loop_agent(
            event=MagicMock(),
            agent_context=MagicMock(),
            chat_provider_id="p1",
            **kwargs,
        )
    return runner.request


@pytest.mark.asyncio
async def test_extra_user_content_parts_is_forwarded():
    part = TextPart(text="当前时间 2026-09-26 17:00").mark_as_temp()
    request = await _run_tool_loop_agent(extra_user_content_parts=[part])

    assert len(request.extra_user_content_parts) == 1
    forwarded = request.extra_user_content_parts[0]
    assert forwarded.text == "当前时间 2026-09-26 17:00"
    assert forwarded._no_save is True


@pytest.mark.asyncio
async def test_extra_user_content_parts_defaults_to_empty():
    request = await _run_tool_loop_agent()

    assert request.extra_user_content_parts == []


@pytest.mark.asyncio
async def test_dict_parts_are_coerced():
    request = await _run_tool_loop_agent(
        extra_user_content_parts=[{"type": "text", "text": "临时检索线索"}]
    )

    # ProviderRequest 是 dataclass，不做类型强转：dict 原样保留，
    # 由下游消费处按 type 分派（见 provider/entities.py 的 content_blocks 构造）。
    assert request.extra_user_content_parts == [
        {"type": "text", "text": "临时检索线索"}
    ]
