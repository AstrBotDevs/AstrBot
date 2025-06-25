import os
import uuid
import wave

from google import genai
from google.genai import types

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "gemini_tts", "Gemini TTS API", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderGeminiTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        api_key: str = provider_config.get("gemini_tts_api_key", "")
        api_base: str | None = provider_config.get("gemini_tts_api_base")
        timeout: int = int(provider_config.get("gemini_tts_timeout", 20))
        http_options = types.HttpOptions(timeout=timeout * 1000)

        if api_base:
            if api_base.endswith("/"):
                api_base = api_base[:-1]
            http_options.base_url = api_base

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio
        self.model: str = provider_config.get(
            "gemini_tts_model", "gemini-2.5-flash-preview-tts"
        )
        self.prefix: str | None = provider_config.get(
            "gemini_tts_prefix",
        )
        self.voice_name: str = provider_config.get("gemini_tts_voice_name", "Leda")

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        path = os.path.join(temp_dir, f"gemini_tts_{uuid.uuid4()}.wav")
        if self.prefix:
            prompt = f"{self.prefix}: {text}"
        else:
            prompt = text
        response = await self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.voice_name,
                        )
                    )
                ),
            ),
        )

        # 不想看类型检查报错
        if (
            not response.candidates
            or not response.candidates[0].content
            or not response.candidates[0].content.parts
            or not response.candidates[0].content.parts[0].inline_data
            or not response.candidates[0].content.parts[0].inline_data.data
        ):
            raise Exception("No audio content returned from Gemini TTS API.")

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(response.candidates[0].content.parts[0].inline_data.data)

        if not os.path.exists(path):
            raise Exception(f"Failed to save audio to {path}.")

        return path
