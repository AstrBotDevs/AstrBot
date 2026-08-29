import asyncio
from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.agent.llm_types import LLMResponse
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    get_agent_error_message,
)
from astrbot.core.utils.error_redaction import safe_error

AgentRunner = ToolLoopAgentRunner[AstrAgentContext]


def _should_stop_agent(astr_event) -> bool:
    return astr_event.is_stopped() or bool(astr_event.get_extra("agent_stop_requested"))


def _truncate_tool_result(text: str, limit: int = 70) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3]}..."


def _extract_chain_json_data(msg_chain: MessageChain) -> dict | None:
    if not msg_chain.chain:
        return None
    first_comp = msg_chain.chain[0]
    if isinstance(first_comp, Json) and isinstance(first_comp.data, dict):
        return first_comp.data
    return None


def _record_tool_call_name(
    tool_info: dict | None, tool_name_by_call_id: dict[str, str]
) -> None:
    if not isinstance(tool_info, dict):
        return
    tool_call_id = tool_info.get("id")
    tool_name = tool_info.get("name")
    if tool_call_id is None or tool_name is None:
        return
    tool_name_by_call_id[str(tool_call_id)] = str(tool_name)


def _build_tool_call_status_message(tool_info: dict | None) -> str:
    if tool_info:
        return f"🔨 调用工具: {tool_info.get('name', 'unknown')}"
    return "🔨 调用工具..."


def _build_tool_result_status_message(
    msg_chain: MessageChain, tool_name_by_call_id: dict[str, str]
) -> str:
    tool_name = "unknown"
    tool_result = ""

    result_data = _extract_chain_json_data(msg_chain)
    if result_data:
        tool_call_id = result_data.get("id")
        if tool_call_id is not None:
            tool_name = tool_name_by_call_id.pop(str(tool_call_id), "unknown")
        tool_result = str(result_data.get("result", ""))

    if not tool_result:
        tool_result = msg_chain.get_plain_text(with_other_comps_mark=True)
    tool_result = _truncate_tool_result(tool_result, 70)

    status_msg = f"🔨 调用工具: {tool_name}"
    if tool_result:
        status_msg = f"{status_msg}\n📎 返回结果: {tool_result}"
    return status_msg


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


async def _handle_tool_event(
    resp,
    astr_event,
    tool_name_by_call_id: dict[str, str],
    show_tool_use: bool,
    show_tool_call_result: bool,
) -> bool:
    """Handle a tool event and report whether it was consumed."""
    if resp.type == "tool_call_result":
        msg_chain = resp.data["chain"]
        astr_event.trace.record(
            "agent_tool_result",
            tool_result=msg_chain.get_plain_text(with_other_comps_mark=True),
        )
        if msg_chain.type == "tool_direct_result":
            await astr_event.send(msg_chain)
        elif astr_event.get_platform_id() == "webchat":
            await astr_event.send(msg_chain)
        elif show_tool_use and show_tool_call_result:
            status_msg = _build_tool_result_status_message(
                msg_chain, tool_name_by_call_id
            )
            await astr_event.send(MessageChain(type="tool_call").message(status_msg))
        return True

    if resp.type != "tool_call":
        return False

    tool_info = _extract_chain_json_data(resp.data["chain"])
    astr_event.trace.record(
        "agent_tool_call", tool_name=tool_info if tool_info else "unknown"
    )
    _record_tool_call_name(tool_info, tool_name_by_call_id)

    if astr_event.get_platform_name() == "webchat":
        await astr_event.send(resp.data["chain"])
    elif show_tool_use and not (show_tool_call_result and isinstance(tool_info, dict)):
        chain = MessageChain(type="tool_call").message(
            _build_tool_call_status_message(tool_info)
        )
        await astr_event.send(chain)

    return True


def _get_streaming_error_chain(
    resp,
    agent_runner: AgentRunner,
    stream_to_general: bool,
    astr_event,
) -> MessageChain | None:
    if resp.type != "err" or not agent_runner.streaming or stream_to_general:
        return None
    return MessageChain().message(get_agent_error_message(astr_event))


async def _emit_agent_response(
    resp,
    *,
    agent_runner: AgentRunner,
    astr_event,
    tool_name_by_call_id: dict[str, str],
    show_tool_use: bool,
    show_tool_call_result: bool,
    stream_to_general: bool,
    show_reasoning: bool,
    can_buffer_llm_result: bool,
    buffered_llm_chains: list[MessageChain],
) -> AsyncGenerator[MessageChain | None]:
    """Handle one non-aborted runner response in its original delivery order."""
    if resp.type == "agent_stats":
        if astr_event.get_platform_name() == "webchat":
            try:
                await astr_event.send(resp.data["chain"])
            except Exception as exc:
                logger.error(
                    "Failed to send agent statistics: %s",
                    safe_error("", exc),
                )
        return

    if resp.type == "tool_call" and agent_runner.streaming and show_tool_use:
        yield MessageChain(chain=[], type="break")

    if await _handle_tool_event(
        resp,
        astr_event,
        tool_name_by_call_id,
        show_tool_use,
        show_tool_call_result,
    ):
        return

    if resp.type == "llm_sources":
        if astr_event.get_platform_name() == "webchat":
            await astr_event.send(resp.data["chain"])
        return

    if resp.type == "llm_result" and resp.data["chain"].type == "reasoning":
        return
    if stream_to_general and resp.type == "streaming_delta":
        return

    error_chain = _get_streaming_error_chain(
        resp,
        agent_runner,
        stream_to_general,
        astr_event,
    )
    if error_chain:
        yield error_chain
        return

    if stream_to_general or not agent_runner.streaming:
        response_chain = (
            MessageChain().message(get_agent_error_message(astr_event))
            if resp.type == "err"
            else resp.data["chain"]
        )
        if can_buffer_llm_result and resp.type == "llm_result":
            buffered_llm_chains.append(response_chain)
            return
        result_content_type = (
            ResultContentType.LLM_RESULT
            if resp.type == "llm_result"
            else ResultContentType.GENERAL_RESULT
        )
        astr_event.set_result(
            MessageEventResult(
                chain=response_chain.chain,
                result_content_type=result_content_type,
            ),
        )
        yield response_chain
        astr_event.clear_result()
        return

    if resp.type == "streaming_delta":
        chain = resp.data["chain"]
        if chain.type != "reasoning" or show_reasoning:
            yield chain


async def _emit_buffered_llm_result(
    buffered_llm_chains: list[MessageChain], astr_event
) -> AsyncGenerator[MessageChain]:
    """Emit buffered ordinary LLM output as a single durable result."""
    merged_chain = _merge_buffered_llm_chains(buffered_llm_chains)
    if merged_chain is None:
        return
    astr_event.set_result(
        MessageEventResult(
            chain=merged_chain.chain,
            result_content_type=ResultContentType.LLM_RESULT,
        ),
    )
    yield merged_chain
    astr_event.clear_result()


def _prepare_forced_final_step(
    agent_runner: AgentRunner, step_idx: int, max_step: int
) -> None:
    """Disable tools and append the final-summary prompt at the step limit."""
    if step_idx != max_step + 1:
        return
    logger.warning(
        "Agent reached max steps (%s), forcing a final response.",
        max_step,
    )
    if agent_runner.done():
        return
    if agent_runner.req:
        agent_runner.req.func_tool = None
    agent_runner.run_context.messages.append(
        Message(
            role="user",
            content="工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。",
        )
    )


async def _complete_agent_step(agent_runner: AgentRunner, astr_event) -> bool:
    """Report whether the runner is complete."""
    return agent_runner.done()


async def run_agent(
    agent_runner: AgentRunner,
    max_step: int = 30,
    show_tool_use: bool = True,
    show_tool_call_result: bool = False,
    stream_to_general: bool = False,
    show_reasoning: bool = False,
    buffer_intermediate_messages: bool = False,
) -> AsyncGenerator[MessageChain | None]:
    step_idx = 0
    astr_event = agent_runner.run_context.context.event
    tool_name_by_call_id: dict[str, str] = {}
    buffered_llm_chains: list[MessageChain] = []
    can_buffer_llm_result = _should_buffer_llm_result(
        buffer_intermediate_messages,
        stream_to_general,
        agent_runner,
    )
    try:
        while step_idx < max_step + 1:
            step_idx += 1
            _prepare_forced_final_step(agent_runner, step_idx, max_step)

            stop_watcher = asyncio.create_task(
                _watch_agent_stop_signal(agent_runner, astr_event),
            )
            try:
                async for resp in agent_runner.step():
                    if _should_stop_agent(astr_event):
                        agent_runner.request_stop()
                    if resp.type == "aborted":
                        # Buffered output is intentionally transient. A stop
                        # must not turn an unfinished response into a durable
                        # UI result or persisted assistant history.
                        buffered_llm_chains.clear()
                        astr_event.set_extra("agent_user_aborted", True)
                        astr_event.set_extra("agent_stop_requested", False)
                        return
                    if _should_stop_agent(astr_event):
                        continue

                    async for chain in _emit_agent_response(
                        resp,
                        agent_runner=agent_runner,
                        astr_event=astr_event,
                        tool_name_by_call_id=tool_name_by_call_id,
                        show_tool_use=show_tool_use,
                        show_tool_call_result=show_tool_call_result,
                        stream_to_general=stream_to_general,
                        show_reasoning=show_reasoning,
                        can_buffer_llm_result=can_buffer_llm_result,
                        buffered_llm_chains=buffered_llm_chains,
                    ):
                        yield chain

                if can_buffer_llm_result and agent_runner.done():
                    async for chain in _emit_buffered_llm_result(
                        buffered_llm_chains, astr_event
                    ):
                        yield chain
                if await _complete_agent_step(agent_runner, astr_event):
                    break
            finally:
                if not stop_watcher.done():
                    stop_watcher.cancel()
                await asyncio.gather(stop_watcher, return_exceptions=True)
    except Exception as e:
        logger.error(
            "Agent execution failed: %s",
            safe_error("", e),
        )
        err_msg = get_agent_error_message(astr_event)

        error_llm_response = LLMResponse(
            role="err",
            completion_text=err_msg,
        )
        try:
            await agent_runner.agent_hooks.on_agent_done(
                agent_runner.run_context, error_llm_response
            )
        except Exception as hook_error:
            logger.error(
                "Error in on_agent_done hook: %s",
                safe_error("", hook_error),
            )

        if agent_runner.streaming:
            yield MessageChain().message(err_msg)
        else:
            astr_event.set_result(MessageEventResult().message(err_msg))


async def _watch_agent_stop_signal(agent_runner: AgentRunner, astr_event) -> None:
    while not agent_runner.done():
        if _should_stop_agent(astr_event):
            agent_runner.request_stop()
            return
        await asyncio.sleep(0.5)
