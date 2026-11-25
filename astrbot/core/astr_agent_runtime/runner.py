import asyncio
import traceback
from collections.abc import AsyncGenerator
from contextlib import aclosing

from astrbot.core import logger
from astrbot.core.agent.events import (
    MessageCompleted,
    ReasoningDelta,
    TextDelta,
    ToolFinished,
    ToolRejected,
    ToolStarted,
)
from astrbot.core.agent.message import Message
from astrbot.core.agent.output import PlainOutput, ReasoningOutput
from astrbot.core.agent.response import AgentResponse
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent_output import (
    _build_tool_call_status_message,
    _build_tool_result_status_message,
    _extract_chain_json_data,
    _record_tool_call_name,
)
from astrbot.core.agent_output_content import chain_from_content
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.speech_output import _simulated_stream_tts as _simulated_stream_tts

AgentRunner = ToolLoopAgentRunner[AstrAgentContext]


def _should_stop_agent(astr_event) -> bool:
    signal = astr_event.get_extra("_background_stop_signal")
    return (
        astr_event.is_stopped()
        or bool(astr_event.get_extra("agent_stop_requested"))
        or (isinstance(signal, asyncio.Event) and signal.is_set())
    )


def _should_buffer_llm_result(
    buffer_intermediate_messages: bool,
    stream_to_general: bool,
    agent_runner: AgentRunner,
) -> bool:
    return (
        buffer_intermediate_messages
        and not stream_to_general
        and not agent_runner.streaming
    )


def _merge_buffered_llm_chains(
    buffered_llm_chains: list[MessageChain],
) -> MessageChain | None:
    if not buffered_llm_chains:
        return None

    merged_chain = MessageChain()
    for chain in buffered_llm_chains:
        merged_chain.chain.extend(chain.chain)
    buffered_llm_chains.clear()
    return merged_chain


async def run_agent(
    agent_runner: AgentRunner,
    max_step: int = 128,
    show_tool_use: bool = True,
    show_tool_call_result: bool = False,
    stream_to_general: bool = False,
    show_reasoning: bool = False,
    buffer_intermediate_messages: bool = False,
) -> AsyncGenerator[MessageChain | None, None]:
    """Drive an agent and forward its output to the message pipeline.

    Args:
        agent_runner: Initialized runner to execute.
        max_step: Step budget before forcing a final response.
        show_tool_use: Whether to display tool status.
        show_tool_call_result: Whether to display tool results.
        stream_to_general: Whether to collect streaming output into ordinary replies.
        show_reasoning: Whether to emit reasoning text.
        buffer_intermediate_messages: Whether to buffer intermediate text replies.

    Yields:
        Output chains for delivery by the message pipeline.
    """
    emitted_messages: set[str] = set()
    emitted_reasoning: set[str] = set()
    step_idx = 0
    agent_runner._step_budget_max = max_step
    agent_runner._step_budget_used = 0
    agent_runner._step_budget_notified = set()
    astr_event = agent_runner.run_context.context.event
    tool_name_by_call_id: dict[str, str] = {}
    buffered_llm_chains: list[MessageChain] = []
    can_buffer_llm_result = _should_buffer_llm_result(
        buffer_intermediate_messages,
        stream_to_general,
        agent_runner,
    )
    while step_idx < max_step + 1:
        step_idx += 1

        if step_idx == max_step + 1:
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response."
            )
            if not agent_runner.done():
                agent_runner.run_context.run_end_reason = "max_steps"
                # 拔掉所有工具
                if agent_runner.req:
                    agent_runner.req.func_tool = None
                # 注入提示词
                agent_runner.run_context.messages.append(
                    Message(
                        role="user",
                        content=ToolLoopAgentRunner.MAX_STEPS_REACHED_PROMPT,
                    )
                )

        stop_watcher = asyncio.create_task(
            _watch_agent_stop_signal(agent_runner, astr_event),
        )
        try:
            async with aclosing(agent_runner.step()) as responses:
                async for resp in responses:
                    if not isinstance(resp, AgentResponse):
                        payload = resp
                        if isinstance(payload, (TextDelta, ReasoningDelta)):
                            (
                                emitted_reasoning
                                if isinstance(payload, ReasoningDelta)
                                else emitted_messages
                            ).add(payload.message_id)
                            resp = AgentResponse(
                                type="streaming_delta",
                                data={
                                    "chain": MessageChain(
                                        type="reasoning"
                                        if isinstance(payload, ReasoningDelta)
                                        else None
                                    ).message(payload.text)
                                },
                            )
                        elif isinstance(payload, MessageCompleted):
                            if (
                                agent_runner.streaming
                                and not stream_to_general
                                and show_reasoning
                                and payload.message_id not in emitted_reasoning
                            ):
                                reasoning = "".join(
                                    part.text or ""
                                    for part in payload.content
                                    if isinstance(part, ReasoningOutput)
                                )
                                if reasoning:
                                    yield MessageChain(type="reasoning").message(
                                        reasoning
                                    )
                            content = tuple(
                                part
                                for part in payload.content
                                if not isinstance(part, ReasoningOutput)
                            )
                            if (
                                agent_runner.streaming
                                and not stream_to_general
                                and payload.message_id in emitted_messages
                            ):
                                content = tuple(
                                    part
                                    for part in content
                                    if not isinstance(part, PlainOutput)
                                )
                            if not content:
                                continue
                            resp = AgentResponse(
                                type="streaming_delta"
                                if agent_runner.streaming and not stream_to_general
                                else "llm_result",
                                data={"chain": chain_from_content(content)},
                            )
                        elif isinstance(payload, ToolStarted):
                            resp = AgentResponse(
                                type="tool_call",
                                data={
                                    "chain": MessageChain(
                                        type="tool_call",
                                        chain=[
                                            Json(
                                                data={
                                                    "id": payload.call_id,
                                                    "name": payload.name,
                                                    "args": payload.arguments,
                                                }
                                            )
                                        ],
                                    )
                                },
                            )
                        elif isinstance(payload, (ToolFinished, ToolRejected)):
                            resp = AgentResponse(
                                type="tool_call_result",
                                data={
                                    "chain": MessageChain(
                                        type="tool_call_result",
                                        chain=[
                                            Json(
                                                data={
                                                    "id": payload.call_id,
                                                    "result": "".join(
                                                        part.text
                                                        for part in payload.content
                                                        if isinstance(part, PlainOutput)
                                                    ),
                                                }
                                            )
                                        ],
                                    )
                                },
                            )
                        else:
                            continue
                    if _should_stop_agent(astr_event):
                        agent_runner.request_stop()

                    if resp.type == "aborted":
                        if can_buffer_llm_result:
                            merged_chain = _merge_buffered_llm_chains(
                                buffered_llm_chains
                            )
                            if merged_chain:
                                astr_event.set_result(
                                    MessageEventResult(
                                        chain=merged_chain.chain,
                                        result_content_type=ResultContentType.LLM_RESULT,
                                    ),
                                )
                                yield merged_chain
                                astr_event.clear_result()
                        astr_event.set_extra("agent_user_aborted", True)
                        astr_event.set_extra("agent_stop_requested", False)
                        return

                    if _should_stop_agent(astr_event):
                        continue

                    if resp.type == "agent_stats":
                        if astr_event.get_platform_name() == "webchat":
                            await astr_event.send(resp.data["chain"])
                        continue

                    if resp.type == "tool_call_result":
                        msg_chain = resp.data["chain"]

                        astr_event.trace.record(
                            "agent_tool_result",
                            tool_result=msg_chain.get_plain_text(
                                with_other_comps_mark=True
                            ),
                        )

                        if msg_chain.type == "tool_direct_result":
                            # tool_direct_result 用于标记 llm tool 需要直接发送给用户的内容
                            await astr_event.send(msg_chain)
                            continue
                        if astr_event.get_platform_id() == "webchat":
                            await astr_event.send(msg_chain)
                        elif show_tool_use and show_tool_call_result:
                            status_msg = _build_tool_result_status_message(
                                msg_chain, tool_name_by_call_id
                            )
                            await astr_event.send(
                                MessageChain(type="tool_call").message(status_msg)
                            )
                        # 对于其他情况，暂时先不处理
                        continue
                    elif resp.type == "tool_call":
                        if agent_runner.streaming and show_tool_use:
                            # 向下游平台发送 "break" 分段信号（空 MessageChain，不携带数据）。
                            # 平台适配器收到后会关闭当前流式消息，并在后续文本到来时创建新消息。
                            # 仅在 show_tool_use 为 True 时才发送：此时紧接着会通过
                            # astr_event.send() 独立发送工具状态消息（如"🔨 调用工具: xxx"），
                            # 需要分段才能保证消息顺序正确。
                            # 若 show_tool_use 为 False，不会有独立消息插入，无需分段。
                            yield MessageChain(chain=[], type="break")

                        tool_info = _extract_chain_json_data(resp.data["chain"])
                        astr_event.trace.record(
                            "agent_tool_call",
                            tool_name=tool_info if tool_info else "unknown",
                        )
                        _record_tool_call_name(tool_info, tool_name_by_call_id)

                        if astr_event.get_platform_name() == "webchat":
                            await astr_event.send(resp.data["chain"])
                        elif show_tool_use:
                            if show_tool_call_result and isinstance(tool_info, dict):
                                # Delay tool status notification until tool_call_result.
                                continue
                            chain = MessageChain(type="tool_call").message(
                                _build_tool_call_status_message(tool_info)
                            )
                            await astr_event.send(chain)
                        continue
                    elif resp.type == "llm_result":
                        chain = resp.data["chain"]
                        if chain.type == "reasoning":
                            # For non-streaming mode, we handle reasoning in astrbot/core/astr_agent_runtime/hooks.py.
                            # For streaming mode, we yield content immediately when received a reasoning chunk but not in here, see below.
                            continue

                    if stream_to_general and resp.type == "streaming_delta":
                        continue

                    if (
                        resp.type == "err"
                        and agent_runner.streaming
                        and not stream_to_general
                    ):
                        chain = (
                            resp.data.get("chain")
                            if isinstance(resp.data, dict)
                            else None
                        )
                        if not isinstance(chain, MessageChain):
                            logger.error(
                                "Agent runner returned an error response without a message chain."
                            )
                            chain = MessageChain().message(
                                "Error occurred during AI execution."
                            )
                        yield chain
                        continue

                    if stream_to_general or not agent_runner.streaming:
                        if can_buffer_llm_result and resp.type == "llm_result":
                            buffered_llm_chains.append(resp.data["chain"])
                            continue

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
                        yield resp.data["chain"]
                        astr_event.clear_result()
                    elif resp.type == "streaming_delta":
                        chain = resp.data["chain"]
                        if chain.type == "reasoning" and not show_reasoning:
                            # display the reasoning content only when configured
                            continue
                        yield resp.data["chain"]  # MessageChain

            if (
                isinstance(agent_runner, ToolLoopAgentRunner)
                and agent_runner.was_aborted()
            ):
                astr_event.set_extra("agent_user_aborted", True)
                astr_event.set_extra("agent_stop_requested", False)
            final = (
                agent_runner.get_final_llm_resp()
                if isinstance(agent_runner, ToolLoopAgentRunner)
                else None
            )
            if agent_runner.done() and final is not None and final.role == "err":
                yield MessageChain().message(
                    final.completion_text or "Error occurred during AI execution."
                )
            if can_buffer_llm_result and agent_runner.done():
                merged_chain = _merge_buffered_llm_chains(buffered_llm_chains)
                if merged_chain:
                    astr_event.set_result(
                        MessageEventResult(
                            chain=merged_chain.chain,
                            result_content_type=ResultContentType.LLM_RESULT,
                        ),
                    )
                    yield merged_chain
                    astr_event.clear_result()

            if agent_runner.done():
                break

        except Exception as e:
            logger.error(traceback.format_exc())

            custom_error_message = extract_persona_custom_error_message_from_event(
                astr_event
            )
            if custom_error_message:
                err_msg = custom_error_message
            else:
                err_msg = (
                    f"Error occurred during AI execution.\n"
                    f"Error Type: {type(e).__name__}\n"
                    f"Error Message: {str(e)}"
                )

            if agent_runner.streaming:
                yield MessageChain().message(err_msg)
            else:
                astr_event.set_result(MessageEventResult().message(err_msg))
            return
        finally:
            if not stop_watcher.done():
                stop_watcher.cancel()
            try:
                await asyncio.gather(stop_watcher, return_exceptions=True)
            except asyncio.CancelledError:
                # Cancellation can arrive after a step but before the next one.
                if not agent_runner.done():
                    agent_runner.run_context.run_end_reason = "cancelled"
                    await agent_runner._finish_run()
                raise


async def _watch_agent_stop_signal(agent_runner: AgentRunner, astr_event) -> None:
    while not agent_runner.done():
        if _should_stop_agent(astr_event):
            agent_runner.request_stop()
            return
        await asyncio.sleep(0.5)
