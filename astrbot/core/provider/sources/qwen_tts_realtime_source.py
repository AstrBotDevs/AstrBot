"""Qwen TTS Realtime - WebSocket streaming TTS provider.

Supports models:
- qwen3-tts-flash-realtime (and snapshots)
- qwen3-tts-instruct-flash-realtime (and snapshots, with instructions control)
- qwen-tts-realtime (and snapshots)

Uses dashscope.audio.qwen_tts_realtime.QwenTtsRealtime for WebSocket-based
streaming text-to-speech with low-latency response.
"""

import asyncio
import base64
import os
import threading
import uuid

try:
    from dashscope.audio.qwen_tts_realtime import (
        AudioFormat,
        QwenTtsRealtime,
        QwenTtsRealtimeCallback,
    )
except ImportError:  # pragma: no cover
    QwenTtsRealtime = None
    QwenTtsRealtimeCallback = None
    AudioFormat = None

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


class _QwenRealtimeCallback(QwenTtsRealtimeCallback):
    """Callback for Qwen TTS Realtime WebSocket events."""

    def __init__(self) -> None:
        self.complete_event = threading.Event()
        self._lock = threading.Lock()
        self.audio_chunks: list[bytes] = []
        self.error_msg: str | None = None

    def on_open(self) -> None:
        logger.debug("[QwenTTS Realtime] WebSocket connection opened")

    def on_close(self, close_status_code: int, close_msg: str) -> None:
        logger.debug(
            f"[QwenTTS Realtime] Connection closed: code={close_status_code}, msg={close_msg}",
        )

    def on_event(self, response: dict) -> None:
        try:
            event_type = response.get("type", "")
            if event_type == "session.created":
                session_id = response.get("session", {}).get("id", "unknown")
                logger.debug(f"[QwenTTS Realtime] Session created: {session_id}")
            elif event_type == "response.audio.delta":
                audio_b64 = response.get("delta", "")
                if audio_b64:
                    with self._lock:
                        self.audio_chunks.append(base64.b64decode(audio_b64))
            elif event_type == "response.done":
                logger.debug("[QwenTTS Realtime] Response done")
            elif event_type == "session.finished":
                logger.debug("[QwenTTS Realtime] Session finished")
                self.complete_event.set()
            elif event_type == "error":
                self.error_msg = str(response.get("error", "Unknown error"))
                logger.error(f"[QwenTTS Realtime] Error: {self.error_msg}")
                self.complete_event.set()
        except Exception as e:
            logger.error(f"[QwenTTS Realtime] Callback error: {e}")

    def drain_audio_chunks(self) -> list[bytes]:
        """Thread-safely drain all accumulated audio chunks."""
        with self._lock:
            chunks = self.audio_chunks
            self.audio_chunks = []
            return chunks

    def wait_for_finished(self, timeout: float = 30) -> bool:
        return self.complete_event.wait(timeout=timeout)


@register_provider_adapter(
    "qwen_tts_realtime",
    "Qwen TTS Realtime (WebSocket streaming)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderQwenTTSRealtime(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.voice: str = provider_config.get("qwen_tts_voice", "Cherry")
        self.instructions: str = provider_config.get("qwen_tts_instructions", "")
        self.optimize_instructions: bool = provider_config.get(
            "qwen_tts_optimize_instructions",
            False,
        )
        self.speech_rate: float = provider_config.get("qwen_tts_speech_rate", 1.0)
        self.volume: float = provider_config.get("qwen_tts_volume", 1.0)
        self.pitch_rate: float = provider_config.get("qwen_tts_pitch_rate", 1.0)
        self.qwen_tts_url: str = provider_config.get(
            "qwen_tts_url",
            "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        )
        self.timeout: float = float(provider_config.get("timeout", 30))

        model = provider_config.get("model", "qwen3-tts-flash-realtime")
        self.set_model(model)

        if not self.qwen_tts_url.startswith("wss://"):
            logger.warning(
                f"[QwenTTS Realtime] WebSocket URL 未使用 wss:// 协议: {self.qwen_tts_url}"
            )

    def support_stream(self) -> bool:
        return True

    async def get_audio(self, text: str) -> str:
        """Synthesize speech and return the audio file path."""
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)

        audio_bytes = await self._synthesize(text)
        if not audio_bytes:
            raise RuntimeError(
                "Audio synthesis failed, returned empty content. "
                "The model may not be supported or the service is unavailable.",
            )

        path = os.path.join(temp_dir, f"qwen_tts_realtime_{uuid.uuid4()}.wav")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path

    async def _synthesize(self, text: str) -> bytes | None:
        """Use Qwen TTS Realtime WebSocket API to synthesize speech."""
        if QwenTtsRealtime is None:
            raise RuntimeError(
                "dashscope SDK missing QwenTtsRealtime. "
                "Please upgrade the dashscope package to use Qwen TTS Realtime.",
            )

        callback = _QwenRealtimeCallback()
        model = self.get_model()

        qwen_tts = QwenTtsRealtime(
            model=model,
            callback=callback,
            url=self.qwen_tts_url,
            api_key=self.chosen_api_key,
        )

        loop = asyncio.get_running_loop()

        def _connect_and_send() -> None:
            try:
                qwen_tts.connect()
                kwargs: dict = {
                    "voice": self.voice,
                    "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "mode": "server_commit",
                }
                if self.instructions:
                    kwargs["instructions"] = self.instructions
                    kwargs["optimize_instructions"] = self.optimize_instructions
                if self.speech_rate != 1.0:
                    kwargs["speech_rate"] = self.speech_rate
                if self.volume != 1.0:
                    kwargs["volume"] = self.volume
                if self.pitch_rate != 1.0:
                    kwargs["pitch_rate"] = self.pitch_rate
                qwen_tts.update_session(**kwargs)
                qwen_tts.append_text(text)
                qwen_tts.finish()
            except Exception as e:
                callback.error_msg = str(e)
                callback.complete_event.set()

        await loop.run_in_executor(None, _connect_and_send)
        finished = callback.wait_for_finished(timeout=self.timeout)

        if callback.error_msg:
            logger.error(f"[QwenTTS Realtime] Synthesis error: {callback.error_msg}")
            return None

        if not finished:
            logger.error("[QwenTTS Realtime] Synthesis timeout")
            return None

        # PCM 24000Hz Mono 16bit -> wrap as WAV
        pcm_data = b"".join(callback.audio_chunks)
        if not pcm_data:
            return None
        return self._pcm_to_wav(pcm_data, sample_rate=24000)

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 24000) -> bytes:
        """Convert raw PCM to WAV format."""
        import struct

        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_data)

        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,
            b"WAVE",
            b"fmt ",
            16,
            1,  # PCM
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )
        return header + pcm_data

    async def get_audio_stream(
        self,
        text_queue: asyncio.Queue[str | None],
        audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None],
    ) -> None:
        """Streaming TTS using Qwen TTS Realtime WebSocket API.

        Reads text fragments from text_queue, sends them to the Realtime API
        incrementally, and streams audio chunks to audio_queue as they arrive.
        Sends None to audio_queue when done.
        """
        if QwenTtsRealtime is None:
            raise RuntimeError(
                "dashscope SDK missing QwenTtsRealtime. "
                "Please upgrade the dashscope package to use Qwen TTS Realtime.",
            )

        callback = _QwenRealtimeCallback()
        model = self.get_model()

        qwen_tts = QwenTtsRealtime(
            model=model,
            callback=callback,
            url=self.qwen_tts_url,
            api_key=self.chosen_api_key,
        )

        loop = asyncio.get_running_loop()
        accumulated_text = ""

        # Connect and configure session on background thread
        def _connect() -> None:
            try:
                qwen_tts.connect()
                kwargs: dict = {
                    "voice": self.voice,
                    "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "mode": "server_commit",
                }
                if self.instructions:
                    kwargs["instructions"] = self.instructions
                    kwargs["optimize_instructions"] = self.optimize_instructions
                if self.speech_rate != 1.0:
                    kwargs["speech_rate"] = self.speech_rate
                if self.volume != 1.0:
                    kwargs["volume"] = self.volume
                if self.pitch_rate != 1.0:
                    kwargs["pitch_rate"] = self.pitch_rate
                qwen_tts.update_session(**kwargs)
            except Exception as e:
                callback.error_msg = str(e)
                callback.complete_event.set()

        await loop.run_in_executor(None, _connect)

        if callback.error_msg:
            logger.error(f"[QwenTTS Realtime] Connection error: {callback.error_msg}")
            await audio_queue.put(None)
            return

        # Background collector: periodically drain audio chunks from callback
        # and push to audio_queue
        pcm_buffer: list[bytes] = []
        # ~200ms of audio at 24kHz, 16bit, mono = 9600 bytes
        chunk_threshold = 9600

        async def _collector() -> None:
            while not callback.complete_event.is_set():
                chunks = callback.drain_audio_chunks()
                if chunks:
                    pcm_buffer.extend(chunks)
                    total = sum(len(c) for c in pcm_buffer)
                    if total >= chunk_threshold:
                        pcm_data = b"".join(pcm_buffer)
                        pcm_buffer.clear()
                        wav_data = self._pcm_to_wav(pcm_data, sample_rate=24000)
                        await audio_queue.put(wav_data)
                await asyncio.sleep(0.05)

            # Drain final chunks before exiting
            remaining = callback.drain_audio_chunks()
            if remaining:
                pcm_buffer.extend(remaining)
            if pcm_buffer:
                pcm_data = b"".join(pcm_buffer)
                wav_data = self._pcm_to_wav(pcm_data, sample_rate=24000)
                await audio_queue.put(wav_data)

        collector_task = asyncio.create_task(_collector(), name="qwen_tts_collector")

        try:
            # Main loop: send text fragments to TTS
            while True:
                text_part = await text_queue.get()

                if text_part is None:
                    # End of input: send any accumulated text and finish
                    if accumulated_text:
                        await loop.run_in_executor(
                            None,
                            qwen_tts.append_text,
                            accumulated_text,
                        )
                    await loop.run_in_executor(None, qwen_tts.finish)

                    # Wait for all audio to be generated
                    finished = await loop.run_in_executor(
                        None,
                        callback.wait_for_finished,
                        self.timeout,
                    )
                    if not finished:
                        logger.warning("[QwenTTS Realtime] Streaming timeout")

                    # Signal end of audio stream
                    await audio_queue.put(None)
                    break

                accumulated_text += text_part
                await loop.run_in_executor(
                    None,
                    qwen_tts.append_text,
                    text_part,
                )

        finally:
            collector_task.cancel()
            try:
                await collector_task
            except asyncio.CancelledError:
                pass

            try:
                await loop.run_in_executor(None, qwen_tts.close)
            except Exception:
                pass
