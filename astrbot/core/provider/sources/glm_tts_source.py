import os
import uuid

import aiohttp

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "glm_tts",
    "GLM-TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGLMTTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key: str = provider_config.get("api_key", "")
        if not self.api_key:
            raise ValueError("GLM-TTS requires api_key to be configured")
        self.model_name: str = provider_config.get("model", "glm-tts")
        self.voice: str = provider_config.get("glm_tts_voice", "tongtong")
        self.speed: float = float(provider_config.get("glm_tts_speed", 1.0))
        if not (0.5 <= self.speed <= 2.0):
            self.speed = max(0.5, min(2.0, self.speed))
            logger.warning(
                f"GLM-TTS speed out of range [0.5, 2.0], clamped to {self.speed}"
            )

        self.volume: float = float(provider_config.get("glm_tts_volume", 1.0))
        if not (0 < self.volume <= 10):
            self.volume = max(0.01, min(10.0, self.volume))
            logger.warning(
                f"GLM-TTS volume out of range (0, 10], clamped to {self.volume}"
            )
        self.timeout: int = provider_config.get("timeout", 30)
        self.api_base: str = "https://open.bigmodel.cn/api/paas/v4/audio/speech"

    async def get_audio(self, text: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model_name,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
            "speed": self.speed,
            "volume": self.volume,
        }

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, f"glm_tts_{uuid.uuid4()}.wav")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_base,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    response.raise_for_status()

                    if response.content_type != "audio/wav":
                        error_msg = f"Unexpected content type: {response.content_type}"
                        raise Exception(f"GLM-TTS API error: {error_msg}")

                    audio_data = await response.read()

                    if not audio_data:
                        raise Exception("GLM-TTS API returned empty audio data")

                    with open(output_path, "wb") as f:
                        f.write(audio_data)

                    return output_path

        except aiohttp.ClientError as e:
            raise Exception(f"GLM-TTS API request failed: {e!s}")

    async def terminate(self):
        pass
