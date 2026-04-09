import json
import os
import uuid

from httpx import AsyncClient

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


def _safe_cast(value, type_func, default):
    try:
        return type_func(value)
    except (TypeError, ValueError):
        return default


@register_provider_adapter(
    "typecast_tts",
    "Typecast TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderTypecastTTS(TTSProvider):
    API_URL = "https://api.typecast.ai/v1/text-to-speech"

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)

        self.api_key: str = provider_config.get("api_key", "")
        if not self.api_key:
            raise ValueError("[Typecast TTS] api_key is required")
        self.voice_id: str = provider_config.get("typecast-voice-id", "")
        if not self.voice_id:
            raise ValueError("[Typecast TTS] typecast-voice-id is required")
        self.language: str = provider_config.get("language", "kor")
        VALID_EMOTION_PRESETS = {
            "normal", "happy", "sad", "angry", "whisper", "toneup", "tonedown",
        }
        self.emotion_preset: str = provider_config.get(
            "typecast-emotion-preset", "normal"
        )
        if self.emotion_preset not in VALID_EMOTION_PRESETS:
            logger.warning(
                f"[Typecast TTS] Unknown emotion preset '{self.emotion_preset}', "
                f"falling back to 'normal'. Valid values: {sorted(VALID_EMOTION_PRESETS)}"
            )
            self.emotion_preset = "normal"
        self.emotion_intensity: float = _safe_cast(
            provider_config.get("typecast-emotion-intensity", 1.0), float, 1.0
        )
        self.volume: int = _safe_cast(
            provider_config.get("typecast-volume", 100), int, 100
        )
        self.pitch: int = _safe_cast(
            provider_config.get("typecast-pitch", 0), int, 0
        )
        self.tempo: float = _safe_cast(
            provider_config.get("typecast-tempo", 1.0), float, 1.0
        )
        self.timeout: int = _safe_cast(
            provider_config.get("timeout", 30), int, 30
        )
        self.proxy: str = provider_config.get("proxy", "")

        if self.proxy:
            logger.info(f"[Typecast TTS] Using proxy: {self.proxy}")

        self.set_model(provider_config.get("model", "ssfm-v30"))

    def _build_request_body(self, text: str) -> dict:
        return {
            "voice_id": self.voice_id,
            "text": text,
            "model": self.model_name,
            "language": self.language,
            "prompt": {
                "emotion_type": "preset",
                "emotion_preset": self.emotion_preset,
                "emotion_intensity": self.emotion_intensity,
            },
            "output": {
                "volume": self.volume,
                "audio_pitch": self.pitch,
                "audio_tempo": self.tempo,
                "audio_format": "wav",
            },
        }

    async def get_audio(self, text: str) -> str:
        if not text or not text.strip():
            raise ValueError("[Typecast TTS] text must not be empty")
        if len(text) > 2000:
            raise ValueError(
                f"[Typecast TTS] text length {len(text)} exceeds maximum of 2000 characters"
            )

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"typecast_tts_{uuid.uuid4()}.wav")

        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
        }
        body = self._build_request_body(text)

        async with AsyncClient(
            timeout=self.timeout,
            proxy=self.proxy if self.proxy else None,
        ) as client, client.stream(
            "POST",
            self.API_URL,
            headers=headers,
            json=body,
        ) as response:
            if response.status_code == 200 and response.headers.get(
                "content-type", ""
            ).lower().startswith("audio/"):
                with open(path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                return path

            error_bytes = await response.aread()
            error_text = error_bytes.decode("utf-8", errors="replace")[:1024]
            try:
                error_detail = json.loads(error_text).get("detail", error_text)
            except (json.JSONDecodeError, AttributeError):
                error_detail = error_text
            raise RuntimeError(
                f"Typecast API request failed: status {response.status_code}, "
                f"response: {error_detail}"
            )
