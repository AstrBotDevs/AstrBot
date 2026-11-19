import os
import wave

from google.genai import types

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter
from .gemini_api_common import close_httpx_client, create_genai_async_client


@register_provider_adapter(
    "gemini_tts",
    "Gemini TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
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
        proxy = provider_config.get("proxy", "")

        self.client, self._http_client = create_genai_async_client(
            provider_label="Gemini TTS",
            api_key=api_key,
            request_headers=self.request_headers,
            api_base=api_base,
            timeout=timeout,
            proxy=proxy,
        )
        self.model: str = provider_config.get(
            "gemini_tts_model",
            "gemini-3.8-flash-tts",
        )
        self.prefix: str | None = provider_config.get(
            "gemini_tts_prefix",
        )
        self.voice_name: str = provider_config.get("gemini_tts_voice_name", "Leda")

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        path = os.path.join(temp_dir, f"gemini_tts_{generate_timestamp_id()}.wav")
        prompt = f"{self.prefix}: {text}" if self.prefix else text
        response = await self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.voice_name,
                        ),
                    ),
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

        return path

    async def terminate(self):
        if self.client:
            await self.client.aclose()
        await close_httpx_client(
            getattr(self, "_http_client", None),
            label="Gemini TTS",
        )
        self._http_client = None
