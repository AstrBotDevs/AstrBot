"""CosyVoice TTS provider using DashScope API.

Supports models:
- cosyvoice-v3.5-plus, cosyvoice-v3.5-flash
- cosyvoice-v3-plus, cosyvoice-v3-flash
- cosyvoice-v2, cosyvoice-v1
- sambert-* models

Uses dashscope.audio.tts_v2.SpeechSynthesizer for non-streaming TTS.
"""

import asyncio
import os
import uuid

from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "cosyvoice_tts",
    "CosyVoice TTS (DashScope)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderCosyVoiceTTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.voice: str = provider_config.get("cosyvoice_voice", "longanyang")
        self.speech_rate: float = provider_config.get("cosyvoice_speech_rate", 1.0)
        self.volume: float = provider_config.get("cosyvoice_volume", 1.0)
        self.pitch_rate: float = provider_config.get("cosyvoice_pitch_rate", 1.0)
        self.timeout_ms: float = float(provider_config.get("timeout", 20)) * 1000
        self.base_url: str = provider_config.get(
            "cosyvoice_base_url",
            "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        )

        model = provider_config.get("model", "cosyvoice-v3-flash")
        self.set_model(model)

        if not self.base_url.startswith("wss://"):
            logger.warning(
                f"[CosyVoice TTS] WebSocket URL 未使用 wss:// 协议: {self.base_url}"
            )

    async def get_audio(self, text: str) -> str:
        """Synthesize speech using CosyVoice and return the audio file path."""
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)

        audio_bytes = await self._synthesize(text)
        if not audio_bytes:
            raise RuntimeError(
                f"Audio synthesis failed for model '{self.get_model()}'. "
                "The model may not be supported or the service is unavailable.",
            )

        path = os.path.join(temp_dir, f"cosyvoice_tts_{uuid.uuid4()}.wav")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path

    async def _synthesize(self, text: str) -> bytes | None:
        """Use CosyVoice SpeechSynthesizer to synthesize speech."""
        loop = asyncio.get_running_loop()

        model = self.get_model()
        fmt = AudioFormat.WAV_24000HZ_MONO_16BIT

        synthesizer = SpeechSynthesizer(
            model=model,
            voice=self.voice,
            format=fmt,
            api_key=self.chosen_api_key,
            url=self.base_url,
        )

        audio_bytes = await loop.run_in_executor(
            None,
            synthesizer.call,
            text,
            self.timeout_ms,
        )

        return audio_bytes
