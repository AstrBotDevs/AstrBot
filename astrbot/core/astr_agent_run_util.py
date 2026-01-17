import asyncio
import time
import traceback
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import Json, Plain
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.provider import TTSProvider

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


async def run_live_agent(
    agent_runner: AgentRunner,
    tts_provider: TTSProvider | None = None,
    max_step: int = 30,
    show_tool_use: bool = True,
    show_reasoning: bool = False,
) -> AsyncGenerator[MessageChain | None, None]:
    """Live Mode 的 Agent 运行器，支持流式 TTS

    Args:
        agent_runner: Agent 运行器
        tts_provider: TTS Provider 实例
        max_step: 最大步数
        show_tool_use: 是否显示工具使用
        show_reasoning: 是否显示推理过程

    Yields:
        MessageChain: 包含文本或音频数据的消息链
    """
    support_stream = tts_provider.support_stream() if tts_provider else False

    if support_stream:
        logger.info("[Live Agent] 使用流式 TTS（原生支持 get_audio_stream）")
    elif tts_provider:
        logger.info(
            f"[Live Agent] 使用 TTS（{tts_provider.meta().type} "
            "使用 get_audio，将累积完整文本后生成音频）"
        )

    # 收集 LLM 输出
    llm_stream_chunks: list[MessageChain] = []

    # 运行普通 agent
    async for chain in run_agent(
        agent_runner,
        max_step=max_step,
        show_tool_use=show_tool_use,
        stream_to_general=False,
        show_reasoning=show_reasoning,
    ):
        if chain is not None:
            llm_stream_chunks.append(chain)

    # 如果没有 TTS Provider，直接发送文本
    if not tts_provider:
        for chain in llm_stream_chunks:
            yield chain
        return

    # 处理 TTS
    tts_start_time = time.time()
    tts_first_frame_time = 0.0
    first_chunk_received = False

    if support_stream:
        # 使用流式 TTS
        async for audio_chunk in _process_stream_tts(llm_stream_chunks, tts_provider):
            if not first_chunk_received:
                tts_first_frame_time = time.time() - tts_start_time
                first_chunk_received = True
            yield audio_chunk
    else:
        # 使用完整音频 TTS
        async for audio_chunk in _process_full_tts(llm_stream_chunks, tts_provider):
            if not first_chunk_received:
                tts_first_frame_time = time.time() - tts_start_time
                first_chunk_received = True
            yield audio_chunk
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
                                "duration": tts_duration,
                                "first_frame_time": tts_first_frame_time,
                            }
                        )
                    ],
                )
            )
    except Exception as e:
        logger.error(f"发送 TTS 统计信息失败: {e}")


async def _process_stream_tts(chunks: list[MessageChain], tts_provider):
    """处理流式 TTS"""
    text_queue: asyncio.Queue[str | None] = asyncio.Queue()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    # 启动 TTS 处理任务
    tts_task = asyncio.create_task(
        tts_provider.get_audio_stream(text_queue, audio_queue)
    )

    chunk_size = 50  # 每 50 个字符发送一次给 TTS

    try:
        # 喂文本给 TTS
        feed_task = asyncio.create_task(
            _feed_text_to_tts(chunks, text_queue, chunk_size)
        )

        # 从 TTS 输出队列中读取音频数据
        while True:
            audio_data = await audio_queue.get()

            if audio_data is None:
                break

            # 将音频数据封装为 MessageChain
            import base64

            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

            chain = MessageChain(chain=[Plain(audio_b64)], type="audio_chunk")
            yield chain

        await feed_task

    except Exception as e:
        logger.error(f"[Live TTS] 流式处理失败: {e}", exc_info=True)
        await text_queue.put(None)

    finally:
        try:
            await asyncio.wait_for(tts_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("[Live TTS] TTS 任务超时，强制取消")
            tts_task.cancel()


async def _feed_text_to_tts(
    chunks: list[MessageChain], text_queue: asyncio.Queue, chunk_size: int
):
    """从消息链中提取文本并分块发送给 TTS"""
    accumulated_text = ""

    try:
        for chain in chunks:
            text = chain.get_plain_text()
            if not text:
                continue

            accumulated_text += text

            # 当累积的文本达到chunk_size时，发送给TTS
            while len(accumulated_text) >= chunk_size:
                chunk = accumulated_text[:chunk_size]
                await text_queue.put(chunk)
                accumulated_text = accumulated_text[chunk_size:]

        # 处理剩余文本
        if accumulated_text:
            await text_queue.put(accumulated_text)

    finally:
        # 发送结束标记
        await text_queue.put(None)


async def _process_full_tts(chunks: list[MessageChain], tts_provider):
    """处理完整音频 TTS"""
    accumulated_text = ""

    try:
        # 累积所有文本
        for chain in chunks:
            text = chain.get_plain_text()
            if text:
                accumulated_text += text

        # 如果没有文本，直接返回
        if not accumulated_text:
            return

        logger.info(f"[Live TTS] 累积完整文本，长度: {len(accumulated_text)}")

        # 调用 get_audio 生成完整音频
        audio_path = await tts_provider.get_audio(accumulated_text)

        # 读取音频文件
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        # 将音频数据封装为 MessageChain
        import base64

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        chain = MessageChain(chain=[Plain(audio_b64)], type="audio_chunk")
        yield chain

    except Exception as e:
        logger.error(f"[Live TTS] 完整音频生成失败: {e}", exc_info=True)
