import traceback
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.provider.entities import LLMResponse

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
    while step_idx < max_step + 1:
        step_idx += 1

        if step_idx == max_step + 1:
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response."
            )
            if not agent_runner.done():
                # 拔掉所有工具
                if agent_runner.req:
                    agent_runner.req.func_tool = None
                # 注入提示词
                agent_runner.run_context.messages.append(
                    Message(
                        role="user",
                        content="工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。",
                    )
                )

        try:
            async for resp in agent_runner.step():
                if astr_event.is_stopped():
                    return
                if resp.type == "tool_call_result":
                    msg_chain = resp.data["chain"]
                    if msg_chain.type == "tool_direct_result":
                        # tool_direct_result 用于标记 llm tool 需要直接发送给用户的内容
                        await astr_event.send(msg_chain)
                        continue
                    if astr_event.get_platform_id() == "webchat":
                        await astr_event.send(msg_chain)
                    # 对于其他情况，暂时先不处理
                    continue
                elif resp.type == "tool_call":
                    if agent_runner.streaming:
                        # 用来标记流式响应需要分节
                        yield MessageChain(chain=[], type="break")

                    if astr_event.get_platform_name() == "webchat":
                        await astr_event.send(resp.data["chain"])
                    elif show_tool_use:
                        json_comp = resp.data["chain"].chain[0]
                        if isinstance(json_comp, Json):
                            m = f"🔨 调用工具: {json_comp.data.get('name')}"
                        else:
                            m = "🔨 调用工具..."
                        chain = MessageChain(type="tool_call").message(m)
                        await astr_event.send(chain)
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
                # send agent stats to webchat
                if astr_event.get_platform_name() == "webchat":
                    await astr_event.send(
                        MessageChain(
                            type="agent_stats",
                            chain=[Json(data=agent_runner.stats.to_dict())],
                        )
                    )

                break

        except Exception as e:
            logger.error(traceback.format_exc())

            err_msg = f"\n\nAstrBot 请求失败。\n错误类型: {type(e).__name__}\n错误信息: {e!s}\n\n请在平台日志查看和分享错误详情。\n"

            error_llm_response = LLMResponse(
                role="err",
                completion_text=err_msg,
            )
            try:
                await agent_runner.agent_hooks.on_agent_done(
                    agent_runner.run_context, error_llm_response
                )
            except Exception:
                logger.exception("Error in on_agent_done hook")

            if agent_runner.streaming:
                yield MessageChain().message(err_msg)
            else:
                astr_event.set_result(MessageEventResult().message(err_msg))
            return
