import asyncio
import base64
import logging
import os
import uuid

import aiohttp
import dashscope
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

try:
    from dashscope.aigc.multimodal_conversation import MultiModalConversation
except (
    ImportError
):  # pragma: no cover - older dashscope versions without Qwen TTS support
    MultiModalConversation = None

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

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
        self.set_model(provider_config.get("model"))
        self.timeout_ms = float(provider_config.get("timeout", 20)) * 1000
        dashscope.api_key = self.chosen_api_key

    async def get_audio(self, text: str) -> str:
        model = self.get_model()
        if not model:
            raise RuntimeError("Dashscope TTS model is not configured.")

        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)

        if self._is_qwen_tts_model(model):
            audio_bytes, ext = await self._synthesize_with_qwen_tts(model, text)
        else:
            audio_bytes, ext = await self._synthesize_with_cosyvoice(model, text)

        if not audio_bytes:
            raise RuntimeError(
                "Audio synthesis failed, returned empty content. The model may not be supported or the service is unavailable.",
            )

        path = os.path.join(temp_dir, f"dashscope_tts_{uuid.uuid4()}{ext}")
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
            "text": text,
            "api_key": self.chosen_api_key,
            "voice": self.voice or "Cherry",
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
        loop = asyncio.get_event_loop()
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
                aiohttp.ClientSession() as session,
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
            model=model,
            voice=self.voice,
            format=AudioFormat.WAV_24000HZ_MONO_16BIT,
        )
        loop = asyncio.get_event_loop()
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

    def _is_qwen_tts_model(self, model: str) -> bool:
        model_lower = model.lower()
        return "tts" in model_lower and model_lower.startswith("qwen")
