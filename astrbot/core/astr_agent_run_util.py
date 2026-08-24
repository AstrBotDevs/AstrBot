import asyncio
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from astrbot import logger
from astrbot.core.agent.llm_types import LLMResponse
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import BaseMessageComponent, Json, Plain
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    get_agent_error_message,
)
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.utils.error_redaction import safe_error

AgentRunner = ToolLoopAgentRunner[AstrAgentContext]

# Live TTS is a 3-stage pipeline: feeder -> text_queue -> TTS -> audio_queue.
# Bound the queues so a fast producer cannot grow memory without bound.
# Sentinel None occupies one slot, so maxsize must be >= 2.
_LIVE_TTS_TEXT_QUEUE_MAXSIZE = 16
_LIVE_TTS_AUDIO_QUEUE_MAXSIZE = 8


def _should_stop_agent(astr_event) -> bool:
    return astr_event.is_stopped() or bool(astr_event.get_extra("agent_stop_requested"))


def _current_task_cancelling() -> bool:
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


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


async def run_live_agent(
    agent_runner: AgentRunner,
    tts_provider: TTSProvider | None = None,
    max_step: int = 30,
    show_tool_use: bool = True,
    show_tool_call_result: bool = False,
    show_reasoning: bool = False,
    buffer_intermediate_messages: bool = False,
) -> AsyncGenerator[MessageChain | None]:
    """Live Mode 的 Agent 运行器，支持流式 TTS

    Args:
        agent_runner: Agent 运行器
        tts_provider: TTS Provider 实例
        max_step: 最大步数
        show_tool_use: 是否显示工具使用
        show_tool_call_result: 是否显示工具返回结果
        show_reasoning: 是否显示推理过程

    Yields:
        MessageChain: 包含文本或音频数据的消息链
    """
    # 如果没有 TTS Provider，直接发送文本
    if not tts_provider:
        async for chain in run_agent(
            agent_runner,
            max_step=max_step,
            show_tool_use=show_tool_use,
            show_tool_call_result=show_tool_call_result,
            stream_to_general=False,
            show_reasoning=show_reasoning,
            buffer_intermediate_messages=buffer_intermediate_messages,
        ):
            yield chain
        return

    support_stream = tts_provider.support_stream()
    if support_stream:
        logger.info("[Live Agent] 使用流式 TTS（原生支持 get_audio_stream）")
    else:
        logger.info(
            f"[Live Agent] 使用 TTS（{tts_provider.meta().type} "
            "使用 get_audio，将按句子分块生成音频）"
        )

    # 统计数据初始化
    tts_start_time = time.time()
    tts_first_frame_time = 0.0
    first_chunk_received = False

    # 创建队列
    text_queue: asyncio.Queue[str | None] = asyncio.Queue(
        maxsize=_LIVE_TTS_TEXT_QUEUE_MAXSIZE
    )
    # audio_queue stored bytes or (text, bytes)
    audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None] = asyncio.Queue(
        maxsize=_LIVE_TTS_AUDIO_QUEUE_MAXSIZE
    )

    # 1. 启动 Agent Feeder 任务：负责运行 Agent 并将文本分句喂给 text_queue
    feeder_task = asyncio.create_task(
        _run_agent_feeder(
            agent_runner,
            text_queue,
            max_step,
            show_tool_use,
            show_tool_call_result,
            show_reasoning,
            buffer_intermediate_messages,
        )
    )

    # 2. 启动 TTS 任务：负责从 text_queue 读取文本并生成音频到 audio_queue
    if support_stream:
        tts_task = asyncio.create_task(
            _safe_tts_stream_wrapper(tts_provider, text_queue, audio_queue)
        )
    else:
        tts_task = asyncio.create_task(
            _simulated_stream_tts(
                tts_provider,
                text_queue,
                audio_queue,
                agent_runner.run_context.context.event,
            )
        )

    # 3. 主循环：从 audio_queue 读取音频并 yield
    try:
        while True:
            queue_item = await audio_queue.get()

            if queue_item is None:
                break

            text = None
            if isinstance(queue_item, tuple):
                text, audio_data = queue_item
            else:
                audio_data = queue_item

            if not first_chunk_received:
                # 记录首帧延迟（从开始处理到收到第一个音频块）
                tts_first_frame_time = time.time() - tts_start_time
                first_chunk_received = True

            # 将音频数据封装为 MessageChain
            import base64

            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
            comps: list[BaseMessageComponent] = [Plain(audio_b64)]
            if text:
                comps.append(Json(data={"text": text}))
            chain = MessageChain(chain=comps, type="audio_chunk")
            yield chain

    except Exception as e:
        logger.error("[Live Agent] runtime error: %s", safe_error("", e))
    finally:
        # 清理任务
        if not feeder_task.done():
            feeder_task.cancel()
        if not tts_task.done():
            tts_task.cancel()

        # 确保队列被消费
        pass

    tts_end_time = time.time()

    # 发送 TTS 统计信息
    try:
        astr_event = agent_runner.run_context.context.event
        if astr_event.get_platform_name() == "webchat":
            tts_duration = tts_end_time - tts_start_time
            await astr_event.send(
                MessageChain(
                    type="tts_stats",
                    chain=[
                        Json(
                            data={
                                "tts_total_time": tts_duration,
                                "tts_first_frame_time": tts_first_frame_time,
                                "tts": tts_provider.meta().type,
                                "chat_model": agent_runner.provider.get_model(),
                            }
                        )
                    ],
                )
            )
    except Exception as e:
        logger.error("Failed to send TTS statistics: %s", safe_error("", e))


async def _run_agent_feeder(
    agent_runner: AgentRunner,
    text_queue: asyncio.Queue,
    max_step: int,
    show_tool_use: bool,
    show_tool_call_result: bool,
    show_reasoning: bool,
    buffer_intermediate_messages: bool,
) -> None:
    """运行 Agent 并将文本输出分句放入队列"""
    buffer = ""
    try:
        async for chain in run_agent(
            agent_runner,
            max_step=max_step,
            show_tool_use=show_tool_use,
            show_tool_call_result=show_tool_call_result,
            stream_to_general=False,
            show_reasoning=show_reasoning,
            buffer_intermediate_messages=buffer_intermediate_messages,
        ):
            if chain is None:
                continue

            # 提取文本
            text = chain.get_plain_text()
            if text:
                buffer += text

                # 分句逻辑：匹配标点符号
                # r"([.。!！?？\n]+)" 会保留分隔符
                parts = re.split(r"([.。!！?？\n]+)", buffer)

                if len(parts) > 1:
                    # 处理完整的句子
                    # range step 2 因为 split 后是 [text, delim, text, delim, ...]
                    temp_buffer = ""
                    for i in range(0, len(parts) - 1, 2):
                        sentence = parts[i]
                        delim = parts[i + 1]
                        full_sentence = sentence + delim
                        temp_buffer += full_sentence

                        if len(temp_buffer) >= 10:
                            if temp_buffer.strip():
                                logger.info(f"[Live Agent Feeder] 分句: {temp_buffer}")
                                await text_queue.put(temp_buffer)
                            temp_buffer = ""

                    # 更新 buffer 为剩余部分
                    buffer = temp_buffer + parts[-1]

        # 处理剩余 buffer
        if buffer.strip():
            await text_queue.put(buffer)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("[Live Agent Feeder] Error: %s", safe_error("", e))
    finally:
        if not _current_task_cancelling():
            await text_queue.put(None)


async def _safe_tts_stream_wrapper(
    tts_provider: TTSProvider,
    text_queue: asyncio.Queue[str | None],
    audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None],
) -> None:
    """包装原生流式 TTS 确保异常处理和队列关闭"""
    try:
        await tts_provider.get_audio_stream(text_queue, audio_queue)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("[Live TTS Stream] Error: %s", safe_error("", e))
    finally:
        if not _current_task_cancelling():
            await audio_queue.put(None)


async def _simulated_stream_tts(
    tts_provider: TTSProvider,
    text_queue: asyncio.Queue[str | None],
    audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None],
    astr_event: Any,
) -> None:
    """模拟流式 TTS 分句生成音频.

    Args:
        tts_provider: Provider used to synthesize audio files.
        text_queue: Text chunks to synthesize. ``None`` ends the worker.
        audio_queue: Synthesized audio bytes output queue.
        astr_event: Current event used to cleanup generated TTS files after the
            event finishes.
    """

    try:
        while True:
            text = await text_queue.get()
            if text is None:
                break

            try:
                audio_path = await tts_provider.get_audio(text)

                if audio_path:
                    audio_data = await asyncio.to_thread(Path(audio_path).read_bytes)
                    astr_event.track_temporary_local_file(audio_path)
                    await audio_queue.put((text, audio_data))
            except Exception as e:
                logger.error(
                    "[Live TTS Simulated] Error processing text: %s",
                    safe_error("", e),
                )
                # 继续处理下一句

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("[Live TTS Simulated] Critical Error: %s", safe_error("", e))
    finally:
        if not _current_task_cancelling():
            await audio_queue.put(None)
