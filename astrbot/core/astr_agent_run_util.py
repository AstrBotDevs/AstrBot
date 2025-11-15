import traceback
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)

AgentRunner = ToolLoopAgentRunner[AstrAgentContext]


async def run_agent(
    agent_runner: AgentRunner,
    max_step: int = 30,
    show_tool_use: bool = True,
    stream_to_general: bool = False,
    show_reasoning: bool = False,
) -> AsyncGenerator[MessageChain | None, None]:
    step_idx = 0
    astr_event = agent_runner.run_context.context.event
    while step_idx < max_step:
        step_idx += 1
        try:
            async for resp in agent_runner.step():
                if astr_event.is_stopped():
                    return
                if resp.type == "tool_call_result":
                    msg_chain = resp.data["chain"]
                    if msg_chain.type == "tool_direct_result":
                        # tool_direct_result 用于标记 llm tool 需要直接发送给用户的内容
                        await astr_event.send(resp.data["chain"])
                        continue
                    # 对于其他情况，暂时先不处理
                    continue
                elif resp.type == "tool_call":
                    if agent_runner.streaming:
                        # 用来标记流式响应需要分节
                        yield MessageChain(chain=[], type="break")
                    if show_tool_use:
                        await astr_event.send(resp.data["chain"])
                    continue

                if stream_to_general and resp.type == "streaming_delta":
                    continue

                if stream_to_general or not agent_runner.streaming:
                    content_typ = (
                        ResultContentType.LLM_RESULT
                        if resp.type == "llm_result"
                        else ResultContentType.GENERAL_RESULT
                    )
                    astr_event.set_result(
                        MessageEventResult(
                            chain=resp.data["chain"].chain,
                            result_content_type=content_typ,
                        ),
                    )
                    yield
                    astr_event.clear_result()
                elif resp.type == "streaming_delta":
                    chain = resp.data["chain"]
                    if chain.type == "reasoning" and not show_reasoning:
                        # display the reasoning content only when configured
                        continue
                    yield resp.data["chain"]  # MessageChain
            if agent_runner.done():
                break

        except Exception as e:
            logger.error(traceback.format_exc())
            err_msg = f"\n\nAstrBot 请求失败。\n错误类型: {type(e).__name__}\n错误信息: {e!s}\n\n请在控制台查看和分享错误详情。\n"
            if agent_runner.streaming:
                yield MessageChain().message(err_msg)
            else:
                astr_event.set_result(MessageEventResult().message(err_msg))
            return
