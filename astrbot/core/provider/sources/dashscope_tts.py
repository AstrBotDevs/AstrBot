import asyncio
import base64
import io
import logging
import os
import threading
import wave

import aiohttp
import dashscope
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

try:
    from dashscope.aigc.multimodal_conversation import MultiModalConversation
except (
    ImportError
):  # pragma: no cover - older dashscope versions without Qwen TTS support
    MultiModalConversation = None

try:
    from dashscope.audio.qwen_tts_realtime import (
        QwenTtsRealtime,
        QwenTtsRealtimeCallback,
    )
except (
    ImportError
):  # pragma: no cover - older dashscope versions without realtime TTS support
    QwenTtsRealtime = None
    QwenTtsRealtimeCallback = object

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "dashscope_tts",
    "Dashscope TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderDashscopeTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.voice: str = provider_config.get("dashscope_tts_voice", "loongstella")
        self.set_model(provider_config["model"])
        self.timeout_ms = float(provider_config.get("timeout", 20)) * 1000
        dashscope.api_key = self.chosen_api_key

    async def get_audio(self, text: str) -> str:
        model = self.get_model()
        if not model:
            raise RuntimeError("Dashscope TTS model is not configured.")

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)

        if self._is_qwen_tts_realtime_model(model):
            audio_bytes, ext = await self._synthesize_with_qwen_tts_realtime(
                model, text
            )
        elif self._is_qwen_tts_model(model):
            audio_bytes, ext = await self._synthesize_with_qwen_tts(model, text)
        else:
            audio_bytes, ext = await self._synthesize_with_cosyvoice(model, text)

        if not audio_bytes:
            raise RuntimeError(
                "Audio synthesis failed, returned empty content. The model may not be supported or the service is unavailable.",
            )

        path = os.path.join(temp_dir, f"dashscope_tts_{generate_timestamp_id()}{ext}")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path

    def _call_qwen_tts(self, model: str, text: str):
        if MultiModalConversation is None:
            raise RuntimeError(
                "dashscope SDK missing MultiModalConversation. Please upgrade the dashscope package to use Qwen TTS models.",
            )

        kwargs = {
            "model": model,
            "headers": self.request_headers.copy(),
            "messages": None,
            "api_key": self.chosen_api_key,
            "voice": self.voice or "Cherry",
            "text": text,
        }
        if not self.voice:
            logging.warning(
                "No voice specified for Qwen TTS model, using default 'Cherry'.",
            )
        return MultiModalConversation.call(**kwargs)

    async def _synthesize_with_qwen_tts(
        self,
        model: str,
        text: str,
    ) -> tuple[bytes | None, str]:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, self._call_qwen_tts, model, text)
        audio_bytes = await self._extract_audio_from_response(response)
        if not audio_bytes:
            raise RuntimeError(
                f"Audio synthesis failed for model '{model}'. {response}",
            )
        ext = ".wav"
        return audio_bytes, ext

    async def _extract_audio_from_response(self, response) -> bytes | None:
        output = getattr(response, "output", None)
        audio_obj = getattr(output, "audio", None) if output is not None else None
        if not audio_obj:
            return None

        data_b64 = getattr(audio_obj, "data", None)
        if data_b64:
            try:
                return base64.b64decode(data_b64)
            except (ValueError, TypeError):
                logging.exception("Failed to decode base64 audio data.")
                return None

        url = getattr(audio_obj, "url", None)
        if url:
            return await self._download_audio_from_url(url)
        return None

    async def _download_audio_from_url(self, url: str) -> bytes | None:
        if not url:
            return None
        timeout = max(self.timeout_ms / 1000, 1) if self.timeout_ms else 20
        try:
            async with (
                aiohttp.ClientSession(
                    headers={"User-Agent": self.request_headers["User-Agent"]}
                ) as session,
                session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response,
            ):
                return await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            logging.exception(f"Failed to download audio from URL {url}: {e}")
            return None

    async def _synthesize_with_cosyvoice(
        self,
        model: str,
        text: str,
    ) -> tuple[bytes | None, str]:
        synthesizer = SpeechSynthesizer(
            headers={
                name.lower(): value for name, value in self.request_headers.items()
            },
            model=model,
            voice=self.voice,
            format=AudioFormat.WAV_24000HZ_MONO_16BIT,
        )
        loop = asyncio.get_running_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            synthesizer.call,
            text,
            self.timeout_ms,
        )
        if not audio_bytes:
            resp = synthesizer.get_response()
            if resp and isinstance(resp, dict):
                raise RuntimeError(
                    f"Audio synthesis failed for model '{model}'. {resp}".strip(),
                )
        return audio_bytes, ".wav"

    def _collect_realtime_audio(
        self,
        model: str,
        text: str,
    ) -> tuple[bytes, str]:
        """Drive one QwenTtsRealtime session and return a WAV byte string.

        ``QwenTtsRealtime`` is a websocket client that receives audio chunks on
        its own thread, so this method is blocking and is meant to be called
        from an executor.
        """
        if QwenTtsRealtime is None:
            raise RuntimeError(
                "dashscope SDK missing QwenTtsRealtime. Please upgrade the dashscope package to use realtime TTS models.",
            )

        chunks: list[bytes] = []
        finished = threading.Event()
        failure: dict[str, str] = {}

        class _CollectingCallback(QwenTtsRealtimeCallback):
            def on_event(self, message: dict) -> None:
                message_type = message.get("type", "")
                if message_type == "response.audio.delta":
                    delta = message.get("delta")
                    if delta:
                        chunks.append(base64.b64decode(delta))
                elif message_type == "response.done":
                    finished.set()
                elif "error" in message_type:
                    failure["message"] = str(
                        message.get("message") or message,
                    )
                    finished.set()

            def on_close(self, close_status_code, close_msg) -> None:
                finished.set()

        client = QwenTtsRealtime(model=model, callback=_CollectingCallback())
        try:
            client.connect()
            client.update_session(voice=self.voice, mode="server_commit")
            client.append_text(text)
            client.commit()
            finished.wait(max(self.timeout_ms / 1000, 30))
        finally:
            try:
                client.close()
            except Exception:
                logging.debug(
                    "Failed to close the realtime TTS websocket, ignoring.",
                    exc_info=True,
                )

        if failure:
            raise RuntimeError(
                f"Realtime audio synthesis failed for model '{model}'. {failure['message']}".strip(),
            )

        pcm = b"".join(chunks)
        if not pcm:
            return b"", ".wav"

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm)
        return buffer.getvalue(), ".wav"

    async def _synthesize_with_qwen_tts_realtime(
        self,
        model: str,
        text: str,
    ) -> tuple[bytes, str]:
        loop = asyncio.get_running_loop()
        audio_bytes, ext = await loop.run_in_executor(
            None,
            self._collect_realtime_audio,
            model,
            text,
        )
        if not audio_bytes:
            raise RuntimeError(
                f"Audio synthesis failed for model '{model}'. No audio was returned by the realtime API.",
            )
        return audio_bytes, ext

    @staticmethod
    def _is_qwen_tts_realtime_model(model: str) -> bool:
        """Realtime TTS models only accept the websocket protocol and cannot be
        called through the HTTP APIs.

        Covers the Qwen3-TTS realtime family (``qwen3-tts-flash-realtime``,
        ``qwen3-tts-vc-realtime-*``, ``qwen3-tts-vd-realtime-*``,
        ``qwen3-tts-instruct-flash-realtime``) as well as the older
        ``qwen-tts-realtime``. ``qwen-audio-*`` models never carry ``-realtime``.
        """
        model_lower = model.lower()
        if "-realtime" not in model_lower:
            return False
        return model_lower.startswith(("qwen3-tts-", "qwen-tts-"))

    def _is_qwen_tts_model(self, model: str) -> bool:
        model_lower = model.lower()
        return "tts" in model_lower and model_lower.startswith("qwen")
