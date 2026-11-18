"""Core-owned sentence buffering and TTS output for arbitrary text streams."""

import asyncio
import base64
import re
import time
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

from astrbot import logger
from astrbot.core.message.components import BaseMessageComponent, Json, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.provider import TTSProvider


async def stream_speech(
    chains: AsyncIterator[MessageChain | None],
    tts_provider: TTSProvider | None,
    *,
    event: AstrMessageEvent,
    model_name: str = "",
) -> AsyncGenerator[MessageChain | None, None]:
    """Synthesize a stream independently from the Agent's execution implementation.

    Args:
        chains: Core's already formatted text output.
        tts_provider: Optional selected TTS provider.
        event: Platform delivery and statistics target.
        model_name: Display metadata; no model execution object is needed.

    Yields:
        Text when no TTS provider is configured, otherwise audio chunks.
    """
    if tts_provider is None:
        async for chain in chains:
            yield chain
        return
    support_stream = tts_provider.support_stream()
    if support_stream:
        logger.info("[Live Agent] Using streaming TTS")
    else:
        logger.info(
            f"[Live Agent] Using sentence-based TTS ({tts_provider.meta().type})"
        )

    tts_start_time = time.time()
    tts_first_frame_time = 0.0
    first_chunk_received = False

    text_queue: asyncio.Queue[str | None] = asyncio.Queue()
    # audio_queue stored bytes or (text, bytes)
    audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None] = asyncio.Queue()

    feeder_task = asyncio.create_task(feed_text(chains, text_queue))

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
            )
        )

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
                tts_first_frame_time = time.time() - tts_start_time
                first_chunk_received = True

            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
            comps: list[BaseMessageComponent] = [Plain(audio_b64)]
            if text:
                comps.append(Json(data={"text": text}))
            chain = MessageChain(chain=comps, type="audio_chunk")
            yield chain

    except Exception as e:
        logger.error(f"[Live Agent] Output failed: {e}", exc_info=True)
    finally:
        if not feeder_task.done():
            feeder_task.cancel()
        if not tts_task.done():
            tts_task.cancel()

        await asyncio.gather(feeder_task, tts_task, return_exceptions=True)

    tts_end_time = time.time()

    try:
        astr_event = event
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
                                "chat_model": model_name
                                or event.get_extra("_agent_chat_model", ""),
                            }
                        )
                    ],
                )
            )
    except Exception as e:
        logger.error(f"Failed to send TTS statistics: {e}")


async def feed_text(
    chains: AsyncIterator[MessageChain | None], text_queue: asyncio.Queue[str | None]
) -> None:
    """Feed complete sentences from an arbitrary output stream to TTS.

    Args:
        chains: Text output independent of any runner.
        text_queue: TTS input queue, terminated on every exit path.
    """
    buffer = ""
    try:
        async for chain in chains:
            if chain is None:
                continue

            text = chain.get_plain_text()
            if text:
                buffer += text

                parts = re.split(r"([.。!！?？\n]+)", buffer)

                if len(parts) > 1:
                    temp_buffer = ""
                    for i in range(0, len(parts) - 1, 2):
                        sentence = parts[i]
                        delim = parts[i + 1]
                        full_sentence = sentence + delim
                        temp_buffer += full_sentence

                        if len(temp_buffer) >= 10:
                            if temp_buffer.strip():
                                logger.info(
                                    f"[Live Agent Feeder] Sentence: {temp_buffer}"
                                )
                                await text_queue.put(temp_buffer)
                            temp_buffer = ""

                    buffer = temp_buffer + parts[-1]

        if buffer.strip():
            await text_queue.put(buffer)

    except Exception as e:
        logger.error(f"[Live Agent Feeder] Error: {e}", exc_info=True)
    finally:
        await text_queue.put(None)


async def _safe_tts_stream_wrapper(
    tts_provider: TTSProvider,
    text_queue: asyncio.Queue[str | None],
    audio_queue: "asyncio.Queue[bytes | tuple[str, bytes] | None]",
) -> None:
    """Close the audio queue on success, cancellation, or provider failure.

    Args:
        tts_provider: Provider producing native streaming audio.
        text_queue: Sentence input terminated by None.
        audio_queue: Audio output terminated on every exit path.
    """
    try:
        await tts_provider.get_audio_stream(text_queue, audio_queue)
    except Exception as e:
        logger.error(f"[Live TTS Stream] Error: {e}", exc_info=True)
    finally:
        await audio_queue.put(None)


async def _simulated_stream_tts(
    tts_provider: TTSProvider,
    text_queue: asyncio.Queue[str | None],
    audio_queue: "asyncio.Queue[bytes | tuple[str, bytes] | None]",
) -> None:
    """Synthesize sentences with a provider that returns complete audio files.

    Args:
        tts_provider: Provider used to synthesize audio files.
        text_queue: Text chunks to synthesize. ``None`` ends the worker.
        audio_queue: Synthesized audio bytes output queue.
    """

    try:
        while True:
            text = await text_queue.get()
            if text is None:
                break

            try:
                audio_path = await tts_provider.get_audio(text)

                if audio_path:
                    audio_data = Path(audio_path).read_bytes()
                    await audio_queue.put((text, audio_data))
            except Exception as e:
                logger.error(
                    f"[Live TTS Simulated] Error processing text '{text[:20]}...': {e}"
                )
                # A failed sentence does not discard subsequent sentences.

    except Exception as e:
        logger.error(f"[Live TTS Simulated] Critical Error: {e}", exc_info=True)
    finally:
        await audio_queue.put(None)
